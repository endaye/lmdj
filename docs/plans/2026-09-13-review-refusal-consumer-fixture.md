# Review refusal artifact consumer regression

## Scope

The collection refusal upload fix `da4ddfc4` introduced an optional failure-only
path. The real-reader success fixture incorrectly requires every upload pattern
except `failure.json` to produce a file. Consequently 53 discovered tests fail
with 10 fixture assertion failures before the consumer runs; evidence:
`/tmp/lmdj-collection-refusal-consumer-red.log`, exit 1.

Model `collection-failure.json` as absent on success, not as an allowed success
archive member. Keep the strict production archive reader unchanged. Add real
consumer tests proving a failure-only archive is ineligible and a valid complete
success archive becomes ineligible if a collection failure fence is added.

Declared files:

- `tests/build/ci_review_wait_test.py`
- `docs/plans/2026-09-13-review-refusal-consumer-fixture.md`

## Verification

Run all current-head review consumer, failure-report consumer and PR workflow
tests; run staged ownership after adding the plan. Independent read-only review
must confirm no production allowlist or eligibility gate is weakened. Fixtures
exercise the actual artifact reader, not live Actions upload or remote review.

### Results

- Current-head review reader 55/55, exit 0:
  `/tmp/lmdj-refusal-consumer-wait.log`.
- Failure-report reader 46/46, exit 0:
  `/tmp/lmdj-refusal-consumer-report.log`.
- Workflow 27 discovered, 26 passed and 1 skipped (pinned actionlint absent),
  exit 0: `/tmp/lmdj-refusal-consumer-workflow.log`.
- Staged ownership 74/74, exit 0: `/tmp/lmdj-refusal-consumer-scope.log`.
- Independent review found no actionable finding and independently repeated
  reader, report and workflow results. Production source is unchanged.

Pitfall disposition: this deterministic fixture branch mismatch is completely
expressed by the producer-shaped archive tests; no process exception is added.

## Version Management

Version impact: none

Reason: test fixture and regression coverage only; no product or runtime change.

## Documentation Impact

Documentation impact: none

Reason: production behavior and Portal facts are unchanged; this repairs the
test's model of the already documented optional collection-refusal artifact.
