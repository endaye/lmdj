# A bounded recheck evidence refusal belongs to one finding, not the whole lane

## Task

PR #1345 head `1f3ac8bd`, controlled by main `f4cc5dc3`, failed the
`Review fallback` lane on every `synchronize` push (runs `34914916246`
attempts 3 and 4, two different Netcup runners, 14 seconds each, no artifact
uploaded). `collect-t2` wrote nothing at all, so the step reported only
`why: review pipeline operation failed; remedy: inspect bounded structured
receipts and retry or review manually`, and no model ever reviewed the head.

The environment was healthy: the same base, head and event environment
reproduce the refusal locally, a `workflow_dispatch` run of the same lane
against the same head completes, and the budget ledger records the engine's
last reconciled provider call. The defect is in the automatic repair-recheck
path that a `synchronize` entry enables.

Each unresolved bot finding authenticates its original review from the retained
producer archive. That archive carries bounded download and expansion budgets
(`review_failure_report.LIMIT`), and this producer archive expands to
4,047,919 bytes against the 4,000,000-byte expansion bound. The refusal
(`why: expanded review archive exceeds budget`) is a reporting error, which the
per-candidate handler did not catch: it escaped `review_recheck.collect_batch`,
aborted complete-input collection, and failed the lane. One finding whose
evidence cannot be authenticated inside its budget became a head nobody could
review.

Declared files:

- `scripts/ci/review_recheck.py`
- `tests/build/ci_review_recheck_test.py`
- `docs/plans/2026-09-15-review-recheck-evidence-budget.md`

Catch the reporting refusal alongside the existing per-candidate refusals and
record that finding as `not_rechecked` with the refusal as its reason. No
budget, timeout, candidate bound, byte bound or evidence requirement is
widened: the archive stays refused, is never fully expanded, and the finding
still receives no recheck verdict. No change to provider selection, prompt,
model, engine, workflow, publication or the publisher's own diagnostics.

## Verification

Baseline: `python3 tests/build/ci_review_recheck_test.py` discovered 40 tests,
all passing, exit 0. The new regression inflates a retained producer archive
past the expansion bound while leaving its deflated payload inside the download
bound, then requires the batch to report every candidate as `not_rechecked`
with the budget refusal and to resolve no thread. Before the fix it fails with
the escaped `ReportingError`; after the fix the complete suite passes. Run the
pipeline, wait, failure-report and adapter suites, and the staged ownership
suite, before commit. No new CI gate and no changed threshold.

Far-side evidence on the real failing input: `collect-t2` for PR #1345 head
`1f3ac8bd` under the `synchronize` environment exits 0, writes the complete
17-file input, and prints both findings as `not_rechecked` with the budget
refusal instead of aborting. That establishes that the engine step now has
complete input to review; this Task does not run the model.

## Remaining gap

`collect-t2`'s unexpected-exception line is still one generic sentence for
every non-publisher command. The publisher gained bounded categories earlier
and collection has not; this Task leaves that unchanged and claims no new
diagnosability.

## Pitfall disposition

Pitfall impact: none — a product-logic refusal whose invariant the new
regression test expresses directly, and no new required check was added.

## Version Management

Version impact: none — CI review adapter behavior only; no Product Build,
Module, Host, Provider or Contract identity is allocated or changed.

## Documentation Impact

Documentation impact: none — no Architecture Portal page, diagram, projected
identity or documented source fact changes, and this plan is not a portal page.
