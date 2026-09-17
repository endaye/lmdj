# Safe review publisher failure diagnostics

## Task

Preserve a bounded error category at the publisher CLI boundary without printing
external exception messages, response bodies, credentials or model output.
PR #1278 run `34744833430/1` completed its model job but failed publication in
0.94 seconds; its runner log retained only the generic exception message.
The downloaded input/configuration and reconstructed result validate locally.
This does not identify the historical remote failure or make that review valid.

Declared files:

- `scripts/ci/review_pipeline.py`
- `tests/build/ci_review_pipeline_test.py`
- `docs/plans/2026-09-13-review-publisher-diagnostics.md`

Keep existing authored validation refusals. For other publisher exceptions,
classify only known exception types and bounded numeric HTTP status, including
the explicit cause chain used by the GitHub adapter. Never stringify those
exceptions, inspect response bodies, or emit class names from arbitrary types.
All other commands keep their current provider-safe generic diagnostics.
Do not change retry behavior, permissions, review eligibility or workflow gates.

## Verification

Lowest-tier regression: invoke the real CLI dispatcher with the real API reader
and an injected HTTP failure; assert exit 1, safe numeric status and no secret
message/body/header/URL. A network failure must differ from an HTTP refusal.
Malformed status, unknown exception and cyclic causes must remain bounded and
secret-safe. Existing publisher refusal and other-command tests remain intact.

- `python3 tests/build/ci_review_pipeline_test.py`
- `python3 tests/build/ci_change_scope_test.py` after staging the new plan.

This tests exception projection, not actual GitHub credentials or outage
recovery. The failed run remains failed. No model calls or GitHub writes are
performed by the tests; a later eligible exact-head review is still required.
The defect is fully expressed by a code regression, so no new Pitfall Ledger
entry is needed.

## Version Management

Version impact: none

Reason: diagnostic-only CI tooling; no Product, Assembly, Host, Module,
Provider or public Contract identity changes and no release operation.

## Documentation Impact

Documentation impact: none

Reason: this changes only the internal exception diagnostic, not any documented
portal workflow, command, release state, identity or authorization contract.
