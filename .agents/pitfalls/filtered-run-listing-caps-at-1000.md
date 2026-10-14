---
id: filtered-run-listing-caps-at-1000
area: ci-release
status: absorbed
recurrences:
  - date: 2026-10-14
    occurrence: https://github.com/endaye/lmdj/issues/1945
    observed_by: claude-opus-5.5
exit: gate:tests/build/ci_cloudflare_preview_budget_test.py
---

# A `created`-filtered Actions run listing silently stops at 1,000 results, so paginating it undercounts without any error.

## Why

GitHub's "list workflow runs" endpoint returns at most 1,000 results whenever
it is filtered by `created`, `event`, `status`, `branch`, `actor`,
`head_sha` or `check_suite_id`. Past the cap a page comes back empty with
`total_count: 0`, which reads exactly like the end of the inventory; the first
page still reports the true `total_count`. Observed live on 2026-10-14:
Self-test Report reported 2,500 runs, served pages 1–10 and an empty page 11.
The Preview budget gate counted month-to-date builds that way; at about 35
builds a day its `created>=` window crosses 1,000 late in the month and the
hosted-minute count would have dropped silently.

## How to apply

Never treat a short or empty page of a filtered run listing as completeness
when the window can hold 1,000 runs. Read the first page's `total_count`,
split the date window while it is at or above 1,000, and fail closed with
why/remedy when a single day still reaches the cap. The budget regression
serves a fake with the real cap and proves the old single listing returned
1,000 of 1,190 runs.
