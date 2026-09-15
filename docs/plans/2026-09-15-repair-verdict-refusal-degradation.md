# A refused repair verdict costs the rechecks, never the head's review

## Task

PR #1344 head `58e26124`, controlled by main `f4cc5dc3`, failed `Review fallback`
on five consecutive attempts (run 34914175883, attempts 1-5) with
`error_class=invalid_output` and
`why: original source quote does not cover the finding anchor`. The three
unresolved bot findings had been collected as repair rechecks.

The engine validates the ordinary review first and completely - closed review
fields, findings list, typed fields, exact changed-path inventory, RIGHT-side
anchors, duplicate locations, summary presence and size - and validates the
repair-verdict section last. That last refusal raised
`EngineError("invalid_output")`, which the attempt boundary turns into
`status: not-reviewed, review: null`. A head whose review had passed every
review rule was therefore published with no review at all, the deterministic
test-scope lane never ran, and the same refusal repeated on every push. The
owner merged #1344 under an exact-head waiver record after a manual disposition
of the three findings; this Task removes the recurring cause instead of relying
on that manual path each time.

Declared files:

- `scripts/ci/pr_agent_review.py`
- `scripts/ci/review_pipeline.py`
- `tests/build/ci_pr_agent_review_test.py`
- `tests/build/ci_review_pipeline_test.py`
- `docs/plans/2026-09-15-repair-verdict-refusal-degradation.md`

`pr_agent_review._validate_native_mapping` now keeps the validated review when
the repair-verdict section is refused. Nothing about the review is relaxed:
every review rule and every bound above is untouched, `validate_repair_verdicts`
itself is unchanged, and the publication paths (`review_recheck.publish` and
`::publish_batch`) still revalidate the same verdicts before any reply or thread
resolution. A refused section can therefore only ever cost the rechecks - not
the review, and never a resolution.

`review_pipeline.publish` treats an authored refusal during recheck publication
as the rechecks' outcome rather than the step's: it saves a bounded refusal
receipt (`lmdj.pr-agent-recheck-refusal.v1`, `status: refused`, one bounded
single-line `why` plus a literal `remedy`) to `repair-recheck.json` and prints
exactly one bounded line. Receipts already persisted by `publish_batch`'s record
callback are carried into the refusal document, so a mid-batch refusal cannot
erase far-side effects. Transport and unresolved-write failures
(`GitHubApiError`, `OSError`, urllib errors) stay fatal: they need
reconciliation, not a receipt.

## Verification

Baseline before the change: `python3 tests/build/ci_review_pipeline_test.py`
discovered 59 tests, 1 skipped, exit 0; `python3
tests/build/ci_pr_agent_review_test.py` discovered 58 tests, 9 skipped, exit 0.

Each new regression fails before the change and passes after:

- engine: a verdict whose `original_quote` is a substring of `original_content`
  but does not cover the finding anchor - `validate_repair_verdicts` still
  refuses it, and `_validate_native_mapping` returns the validated review; a
  review without a model summary still refuses, so the tolerance is local.
- publisher: the corrupted verdict section during `publish` publishes the
  review, writes the bounded refusal receipt, prints one `why:`/`remedy:` line
  and resolves nothing (no API writes, both threads still open).
- publisher: the same degradation for `review_wait.Refused` raised while
  re-authenticating the recheck source, which is the recheck protocol's own
  authored refusal and not a `ReviewScopeError`.
- receipt: capped at 1024 bytes on one line, with a fixed schema, status and
  remedy, and no credential content.

Final: `ci_pr_agent_review_test.py` 59 tests / 9 skipped, `ci_review_pipeline_test.py`
62 / 1, `ci_review_recheck_test.py` 41, `ci_review_wait_test.py` 67,
`ci_review_failure_report_test.py` 46, `ci_change_scope_test.py` 74 - all exit
0 with no new skips, plus the staged ownership suite.

Unexercised: no provider call, no live GitHub write, and no Actions run of this
path, so provider behaviour, workflow permissions and the real artifact upload
of a refusal receipt remain acceptance gaps. A mid-batch refusal that already
persisted some receipts is implemented and documented, but only the no-partial
branch is asserted.

## Pitfall disposition

Pitfall impact: none - a product-logic refusal whose invariant the three new
regression tests express directly, and no new required check was added.

## Version Management

Version impact: none - CI review adapter behaviour only; no Product Build,
Module, Host, Provider or Contract identity is allocated or changed.

## Documentation Impact

Documentation impact: none - no Architecture Portal page, diagram, projected
identity or documented source fact changes; the added file is a plan under
`docs/plans/`.
