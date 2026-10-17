# One bucket for whole-batch missing self-test evidence

## Outcome and authority

Report an incremental batch whose selected execution evidence is missing as a
whole once, in one fixed bucket, instead of one `missing` bucket per selected
suite. This delivers the first remedy of #2338; the owner chose to keep the
policy digest in managed bucket identity and to report whole-batch missing to
one fixed Issue.

## Premise disposition

Fresh main and this Task base are
`e47b02510ef144a518163978d42b44b50558d36b`.

1. **Fan-out — still outstanding.** `plan_batch_reports` turns a
   `missing:<request>` receipt into one `missing` report per selected suite.
   The 64 open `self-test: <suite> missing` Issues are exactly four sets of 16
   (#874–#890, #2049–#2080, #2154–#2175, #2197–#2264). Every observation names
   `Actual failed jobs: none` and the diagnostic this branch alone emits,
   `Selected execution evidence was confirmed missing; no product verdict is
   available.` The ten referenced runs were cancelled or failed as a whole.
2. **Policy digest in the managed key — not a defect; retained.**
   `docs/quality/core-test-policy.md` admits automatic discharge only from a
   later *same-policy* result. Putting the policy digest in the key is how that
   invariant holds: a pass under a changed suite definition must not close a
   failure observed under the old one. #2338 listed it as a defect; that
   premise was wrong. The owner decided to keep it.
3. **Controller timeout — out of this Task.** Why `Incremental batch
   controller` reaches its 25-minute limit is an investigation, recorded under
   #2338. No timeout is changed here.

Job-level missing evidence inside a verdict (a suite whose jobs partly ran)
remains a per-suite `missing` observation; only the whole-batch receipt changes.

## Task and declared files

- `scripts/ci/report_runtime.py`: a whole-batch missing receipt plans one
  unmanaged `BatchMissingReport` keyed `self-test-batch-execution-missing`,
  listing missing and deferred suites. It records, outside the frozen payload,
  the per-suite key/observation pairs the old projection emitted for the same
  receipt — the managed key and the pre-T8b legacy suite key. Delivery skips a
  batch report when any of those pairs is already journaled, so full replay
  never reports a historical batch twice.
- `scripts/ci/self_test_report.py`: the `BATCH_MISSING_KEY` constant.
- `tests/build/ci_report_runtime_test.py`, `tests/build/ci_daily_evidence_test.py`:
  the projection, sharing, replay and historical-supersession facts; the
  claim-starvation test now builds its several reports from real suite failures.
- `apps/docs-site/docs/operations/testing-and-proof.mdx`: state the
  whole-batch missing projection beside the common-event rule.
- This plan.

Managed bucket identity, recovery, causal floors, outbox wire format, journals,
timeouts and lane selection are unchanged. Existing buckets are not closed.

## Verification

- `python3 tests/build/ci_report_runtime_test.py`, `ci_daily_evidence_test.py`,
  `ci_report_outbox_test.py`, `ci_report_progress_test.py`,
  `ci_self_test_report_test.py`, `ci_self_test_report_workflow_test.py`,
  `ci_batch_runtime_test.py`.
- Mutation proofs against the fixed tree, with `__pycache__` cleared and the
  restore written with a fresh mtime and compared byte-for-byte:
  - per-suite fan-out restored in the planner → the projection, sharing,
    replay and supersession tests fail;
  - delivery stops consulting superseded pairs → both supersession subtests
    (managed and legacy key) fail at the no-redelivery assertion;
  - superseded pairs drop the legacy suite key → only the legacy subtest fails.
  The supersession test derives the old keys and observation independently of
  the planner, so a planner omission cannot also hide from the test.
- `scripts/docs-site.sh check` for the Portal page.

Remote acceptance — the next real whole-batch missing receipt reaching the
fixed bucket — is not exercised locally and remains unverified.

## Version Management

Version impact: none — only CI reporting scripts, their tests and documentation
change; no product, module, contract or active manifest identity changes.

## Documentation Impact

Documentation impact: required — the Portal page describing report planning
gains the whole-batch missing projection.

Affected portal pages: /operations/testing-and-proof/

## Pitfall Impact

Pitfall impact: none — the fan-out is visible in the planner and now fixed by
its owning tests; no process invariant outside the code is involved.
