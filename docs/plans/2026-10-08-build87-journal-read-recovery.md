# Build 87 journal read recovery

Relates to #1864. The frozen candidate remains
`5abc52106728f463768210eb4186777a0b44ad7f`.

## Defect and scope

Runs 37662333143/1 and 37663204596/1 refused before product execution
because authenticated historical writer-jobs GETs returned HTTP 502 for two
different writers. Their remaining quotas were 3771 and 2508. The journal
transport disables all secondary retries while holding its writer lock,
including bounded recovery from transient GET errors. One transient read thus
discards a complete history replay's progress. The authenticated checkpoint
after the first failure still matched the complete read-only absence proof.

Separate transient GET recovery from secondary throttling in the existing
retry helper. Keep other callers' default behavior, the existing shared wait
budget, primary-reset cap, deadline and fail-closed authentication. Under the
journal lock, retry only transient REST GET errors within that existing
budget; HTTP 429 still yields immediately. POST/PATCH, including GraphQL
reads, remain single-attempt. Never reuse a failed writer proof or accept a
malformed successful response.

Declared files:

- `scripts/ci/self_test_report.py`
- `scripts/ci/batch_github_journal.py`
- `tests/build/ci_batch_github_journal_test.py`
- `.agents/pitfalls/journal-append-replays-full-history.md`
- this plan

## Verification

Reproduce locked writer authentication failing on one 502 followed by a valid
response before the fix. Assert complete writer validation after retry,
immediate locked 429 refusal, unchanged shared-budget exhaustion, and refusal
of an untrusted writer after transport recovery. Retain existing uncertain
POST/PATCH and GraphQL single-attempt fixtures.

Run transport, self-test report, journal, runtime and incremental-entry suites;
staged ownership and pitfall ledger checks. On the committed input, derive
canonical batch-only keys and retain passing evidence only for unchanged
inputs; execute every changed key. Require authenticated current-head review,
live conversation/protection checks and guarded squash merge.

After merge, authenticate the fixed journal again before supported same-ID
R2 reconciliation. A durable claim and complete current-policy sixteen-suite
verdict are separate far sides; this implementation does not assert either.

## Version Management

Version impact: none. Internal idempotent-read recovery changes no Product,
Host, Module, Provider, Contract or Assembly identity.

Documentation impact: none. No Portal routes, diagrams, projected identities
or product source facts change.
