# Observe actual CI control-plane API work

Relates to #1048 and #979 and the result-driven delivery plan. Run duration
does not measure API requests; the current shared HTTP client retains no
success-side request inventory. Add diagnostics at the actual HTTP boundary,
not estimates from journal length or fake-source call counts.

## Declared files

- `scripts/ci/api_observation.py`
- `scripts/ci/self_test_report.py`
- `scripts/ci/incremental_entry.py`
- `scripts/ci/incremental_completion.py`
- `scripts/ci/report_runtime.py`
- `scripts/ci/review_discovery_runtime.py`
- `tests/build/ci_api_observation_test.py`
- `apps/docs-site/docs/operations/testing-and-proof.mdx`
- This plan.
- `docs/plans/2026-09-09-lmdj-result-driven-delivery.md`

## Behavior and boundaries

The existing CLI processes opt into one thread-safe in-process observation.
All shared-client instances contribute actual opener attempts split into REST,
GraphQL and credential-free artifact download starts. Emit cumulative bounded
JSON checkpoints every 100 completed opener attempts and on normal CLI exit,
including failed operations. Zero-request CLI paths emit nothing. Never output
request paths, headers, bodies, credentials, exception text or artifact URLs.
Keep only closed labels, counters, elapsed time and strictly parsed numeric
rate-limit minima for recognized core/GraphQL/search resources.

Diagnostics cannot authorize writes, infer success or change any request,
retry, timeout, redirect policy, authentication or workflow scheduling. A failed
diagnostic output must not turn a successful business write into a retry.
HTTP response classes count connection responses, not application validation.
Transport failures are counted separately. The credential-free download opener
may follow more redirects; its starts are not a count of every storage hop.

These counters cover the instrumented shared Python client only, not checkout,
Git transport, other actions, model APIs, billing or API cost points. Cumulative
checkpoints must not be summed; retain the last record per process and combine
distinct controller/report/discovery/relay processes with exact run/job evidence.
A missing final record after kill/runner loss is partial evidence, never zero.
Server remaining headers can reset or share a token with other work; minima do
not establish attributable quota consumption. Remote acceptance remains required.

## Verification

First reproduce missing observations through the actual Urllib client. Test
success, HTTP refusal, transport loss, single-attempt POST, retry accounting,
credential-free redirect, malformed/duplicate/untrusted rate headers, concurrent
clients, checkpoints, failed logging, CLI exceptions and clean reset across
invocations. Prove the real four CLI wrappers bind observation; keep existing
entry/report/discovery/relay tests and full CI contract discovery. Run staged and
committed ownership, Portal, version, PR body and range checks. No new required
merge check or widened budget. No new pitfall: the diagnostic gap and limits are
expressible by these regression tests; existing reporting admission pitfall stays.

Local evidence on September 9: 12 observation tests pass, complete CI contract
discovery passes 2,122 tests (pinned actionlint available), staged ownership
passes 66, and Portal passes 112 tests plus its build and 44-route/link check.
A single actual read-only local GitHub request returned the exact requested run
and emitted one REST/2xx observation with numeric core quota metadata. This is
a local CLI/client check, not an Actions-token or whole-workflow cost baseline.

`scripts/version.py verify --version-file products/lmdj/version.json` passes.
The additional full `tests/build/version_test.py` reports a pre-existing main
baseline failure: the slice-points schema introduced in #1049 is missing from
its expected Contract inventory. Those inputs are unchanged from base
`69b41bb4aaffeab8e112c226a9bea3864b977ea9`; retain the failure independently in
Issue 930 comment 5595059590 rather than change Contract code in this Task.
No overall version-suite pass is claimed. Remote counter/cost acceptance still
requires actual post-merge controller/report/discovery/relay runs.

## Version Management

Version impact: none
Reason: additive internal diagnostics only; no Product/Host/Contract/Assembly
identity, allocation, tag or snapshot change.

## Documentation Impact

Documentation impact: required
Affected portal pages: /operations/testing-and-proof
Reason: document how operators interpret actual request counts and their limits.
