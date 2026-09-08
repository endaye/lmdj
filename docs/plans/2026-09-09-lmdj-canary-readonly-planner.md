# T1 — Read-only canary batch planning and record contracts

Status: implementation Task; no activation or external writer.

Parent: [canary implementation plan](2026-09-08-lmdj-canary-versioning-and-promotion.md).
Spec: [candidate design](../design/2026-09-08-lmdj-canary-versioning-and-promotion.md).

## Declared files

- This plan.
- `tools/canary/planning.py`
- `tools/canary/records.py`
- `tools/canary/policy.json`
- `tests/build/ci_canary_planning_test.py`
- `tests/build/ci_canary_records_test.py`
- `scripts/ci/scope_policy.json` (add ownership only).
- `tests/build/ci_change_scope_test.py` (assert new ownership).

## Behavior and boundary

Provide an internal Python library, not a workflow or operator CLI. The planner
reads a pinned target, explicit main/control observations and independently
authenticated progress supplied by its caller. Reuse `GitInputs.policy_at`,
the existing complete first-parent collector and historical-policy union with
dependency closure. Do not execute historical Python or fetch/change Git refs.

Keep version-accounting, each site's successful deployment and formal-publication
baselines separate. Explicit null pointers mean bootstrap; unavailable/corrupt
storage or incomplete Git means error, never no-change. Each non-null pointer
binds a full revision to an opaque durable receipt digest; this library checks
consistency, not the receipt's external authority. Missing adapter/authentication
is an integration gap, not an implicit trusted default.

Return the full version interval, formal-summary interval and each site's own
deployment interval; canonical test-floor selections; naturally affected vs
manually selected sites; and a complete two-Host build set when any Product site
is selected. Force means selected-site preview despite no diff, not permission
to skip gates. The output explicitly says read-only and not admission evidence.
Host IDs/versions are read from the pinned target manifests, not guessed.

Model closed, bounded, digested progress and operation records. The operation
model rejects reused IDs with changed inputs, stale fences and unknown-outcome
re-execution. Pure transition functions do not write storage or prove possession
of a lock. Define a read-only storage port; durable CAS/leases, external receipt
authentication and execution belong to T2/T6. No live scheduler consumes these
records yet. No baseline is advanced by planning.

The v1 suite-to-site projection is conservative, not a claim of minimal runtime
impact. Historical/missing policy uncertainty retains the complete test floor
and all sites. Existing allocation/full-path treatment is unchanged (T3).

## Verification

Write the new tests before the implementation and observe their import failure.
Use temporary real Git repositories for no-change, docs, Host, dependency,
rename/delete/revert, missing old policy, shallow/missing/side-parent baseline,
moving-main and dirty-checkout cases. Test corrupt/duplicate/oversized records,
canonical digests, null vs unavailable, stable request IDs and fenced operation
state transitions. Assertions inspect returned scope/identities and unchanged
Git refs/status, not just successful function return.

- `python3 -m unittest discover -s tests/build -p 'ci_canary_*_test.py'`
- `python3 tests/build/ci_batch_controller_test.py`
- `python3 tests/build/ci_test_scope_test.py`
- `python3 tests/build/ci_change_scope_test.py` after staging new paths.
- Relevant scope differential/consumer parity suites and CI contract discovery.
- Whitespace, final committed-range classification and PR body checks.
- Run the supplied Portal check before commit; do not change portal sources or
  historical snapshots to accommodate the new library.

CI already discovers `ci_*_test.py`; use that registered prefix rather than
adding a test file no runner executes. New `tools/canary/` paths select
`ci_contract` and have an explicit ownership regression. No existing rule or
required check is removed, and no full-CI merge prerequisite is added.

### Local results

- Observed the new suites fail on missing `tools.canary` before implementation.
- All 35 canary planner/record tests pass, including regressions that prevent
  already-delivered other-Host changes and verified empty intervals from
  repeatedly selecting work.
- CI contract discovery: 1,857 tests, successful with one optional actionlint
  semantic-verification test skipped because `LMDJ_ACTIONLINT` is not configured.
  This includes staged new-file ownership and existing collector/scope tests.
- `scripts/architecture-portal.sh check` passes, including production build
  validation of 42 routes and internal links.
- Real temporary Git history is exercised; GitHub receipt authentication,
  remote storage persistence and live canary execution remain unexercised.

## Version Management

Version impact: none

Reason: internal read-only control-plane library and tests only. No Host,
Module, Contract, Provider, Product Build, Assembly, snapshot or artifact changes.
Record schemas are internal operational data, not public product Contracts.

## Documentation Impact

Documentation impact: none

Reason: no user-facing CLI, current Portal page, diagram or projected product
identity changes. This plan describes an internal library with no active
workflow consumer; later operator-facing integration owns portal documentation.

## Acceptance gaps and authority

No AI call, version allocation, changelog generation, durable storage write,
lease/CAS implementation, authenticated remote receipt collection, execution,
signing, tag, Release, deployment, promotion or live rehearsal is delivered.
Pure record model tests do not prove crash-safe external operation. This Task
ships under ordinary commit/push/PR/merge authority only; it enables nothing.
