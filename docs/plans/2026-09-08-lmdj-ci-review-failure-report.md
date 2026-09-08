# PR Review backend failure consumer

## Declared files

- `scripts/ci/review_failure_report.py`
- `tests/build/ci_review_failure_report_test.py`
- This plan.

## Boundary

`collect(api, repository, run_id, attempt)` returns a ReviewFailureReport only
for independently recomputed terminal GLM/Kimi/Grok failures. Valid review,
including findings, and an authenticated closed mapping entry return None;
missing/bad/untrusted receipts raise. `report` applies the existing Report
deduplication API. CLI accepts repository/run-id/attempt/summary. No workflow,
permission, PR API, AI or actual GitHub write occurs in this implementation Task.

Check actual repository/workflow IDs/path, exact completed run attempt, trusted
main control ancestry and source equality, actual producer job and finalize/upload
steps, exact artifact run/head/attempt and closed bounded ZIP. Reuse historical
JSON policies and the existing review protocol to recompute all result and
failure fields, not just a failure.json claim. Overall workflow failure is
expected when the publisher makes the all-backend failure visible.

The unnamed upload's actual API step name `Run actions/upload-artifact@v4` was
observed read-only in original review run 34151840695 on 2026-09-08, together
with successful Review fallback, Save honest final result and upload. This is
step-shape evidence, not an end-to-end reporting acceptance claim.
A collect-only call through the actual UrllibGitHubApi for that completed run
refused its workflow-source/control mismatch before any Issue access. This
confirms the negative real HTTP boundary, not a successful all-failure report.

Use the existing self-test/type:bug/area:ci-release labels and marker format
with a separate stable pr-review/backends-unavailable bucket and exact
PR/head/run/attempt/request observation. Override Report's Issue prose so a
review outage never impersonates a product self-test verdict. Raw model text,
credentials and stderr are never copied into the issue.

The existing apply_report uncertainty fence protects a single process only.
Unknown write responses across processes require the separately implemented
durable reporting outbox; this Task must not claim complete crash recovery.

## Verification

Lowest tier: consumer tests through real T2 protocol and real apply_report with
strict API fixture, followed by complete CI contracts and staged ownership.
Cover valid findings, all failures, closed mapper, wrong identity/source,
partial history, forged failure/result, missing/expired/wrong-run archive and
failed save/upload. Actual private API permissions, webhook wiring, real Issue
publication and cross-process unknown-write recovery remain integration/O1 gaps.

Pitfall impact: reuse real API step shapes; no new incident recurrence claimed.

## Documentation Impact

Documentation impact: none

Reason: Internal CI consumer only; no Portal routes or product identities change.

## Version Management

Version impact: none

Reason: No Product, Module, Provider or Contract version change.
