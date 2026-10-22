# Lane-scoped candidate retry with composed release evidence

## Refreshed premises before edits

Base: `origin/main` at `e9d1047a835371e2fef85682bf04aa602aa74c03` (#2470
merged). Decision: #2422 item 8, Owner confirmed 2026-10-22 (option A of three),
recorded on the issue and in
[`docs/prd/decisions/2026-10-22-candidate-lane-retry.md`](../prd/decisions/2026-10-22-candidate-lane-retry.md).

What holds today and why one flaky lane costs a whole candidate:

- Every layer accepts attempt 1 only: `incremental_batch.identity`,
  `batch_verdict._identity`, `batch_runtime.Runtime`, `batch_reference`,
  `tools/release/verification.py`, `batch_evidence.py`, `verified_recheck.py`.
  A GitHub "re-run jobs" is attempt 2 and is inadmissible everywhere. This
  plan keeps that.
- A candidate request is full selection (`make_request`,
  `batch_verdict.build`, `batch_reference.parse_reference`,
  `batch_evidence._verify`), and `complete-test-v2` admits exactly one passed
  candidate-kind result per target (`verification._candidate_results`); a
  second candidate result for the same target is a hard conflict (#2318).
- The verdict already separates environmental outcomes from test failures:
  `_debt` yields `cancelled`, `infrastructure`, `missing` or `blocked`; a job
  the platform timed out reaches the producer's `needs` as `failure`, so its
  suite outcome is `failed` and only the authenticated jobs API says
  `timed_out` (`batch_evidence_validation.validate_job_observations`).
- `ci.yml` already executes only the lanes the frozen request's execution
  manifest selects, so a focused request runs only its lanes.
- `.github/workflows/self-test-report.yml` passes `batch_request` JSON through
  unchanged; it is an execution source whose digest must stay compatible
  between a frozen control and the executor, so this plan does not edit it.

## Mechanism

A `retry` request is an explicit fair-queue request (like `node` and
`candidate`) that re-runs only the lanes an existing candidate did not pass,
for the same target, with the environmental proof frozen in the request:

```
retry_of = {"request": "<candidate request id>",
            "environmental": {"<suite>": {"outcome": "<original outcome>",
                                          "jobs": {"<job>": "timed_out" | "cancelled"}}}}
```

Admission rules, fail-closed in the reducer and replayed exactly (the
reducer is pure and reference-opaque: it cross-checks outcomes, suite set,
target, policy and once-per-candidate against journal truth; the complete
failing-job set of a `failed` suite is produced by the runtime from the
retained verdict and the jobs API, and re-proven by the release consumer):

- the original is a candidate request for the same target and policy with a
  durable result;
- the retry's suites are exactly the original's non-passed suites (no
  partial retry leaving a gap), listed without dependency closure: a retry
  re-runs lanes, it does not propagate a change;
- each suite's recorded outcome matches the original result; a `failed`
  suite carries every failing job's authenticated API conclusion, each
  `timed_out` or `cancelled`; debt outcomes carry no jobs; a suite with a test
  failure never qualifies;
- one retry per original (which is also once per lane);
- a retry never moves the automatic cursor, never adds debt, and leaves the
  release hold (#2470) untouched because the original candidate result
  already lifted it.

The runtime builds the retry from the operator's command
`{"id","kind":"retry","target","retry_of"}`: it replays the journal, reads
the original result's verdict for the non-passed suites and their failing
jobs, reads the original executor run's jobs from the API, refuses any
failing job whose conclusion is not environmental, and freezes the proof in
the request. Redelivery of the same command reconciles the original request.

PR 2 (release side, separate plan section below) composes the primary
candidate result with its retry into `lmdj.ci-batch-release-reference.v2`.

## PR 1 — journal, controller, verdict and runtime (this Task)

Declared files:

- `scripts/ci/incremental_batch.py`: kind `retry`, `retry_of` in
  `make_request`/`_request`, `ENVIRONMENTAL_CONCLUSIONS`, enqueue rules.
- `scripts/ci/batch_verdict.py`: `retry` is a known request kind; focused
  selection stays allowed for it.
- `scripts/ci/batch_runtime.py`: the explicit `retry` command and
  `retry_request`; policy drift at settlement applies to retries as to
  candidates.
- `tests/build/ci_incremental_batch_test.py`,
  `tests/build/ci_batch_controller_test.py`,
  `tests/build/ci_batch_verdict_test.py`, `tests/build/ci_batch_runtime_test.py`.
- This plan and the decision file.

Lowest-tier tests and the defect each new test catches:

- reducer: a retry without a durable original result, for a passed suite,
  for a `failed` suite without environmental job proof, with a job
  conclusion of `failure`, missing one non-passed suite, for another target,
  or a second retry for the same original is refused; a valid retry is
  queued, and its advance moves no cursor and records no debt.
- controller: a retry request flows through the fair queue and executes
  with its focused selection; the hold of #2470 is unaffected.
- verdict: identity kind `retry` builds and validates with a focused
  selection; `candidate` still requires full.
- runtime: a candidate whose lane the platform timed out (needs `failure`,
  API `timed_out`) settles failed; the retry command freezes the proof from
  the API and enqueues; a lane that failed on a test is refused; the
  redelivered command reconciles the original; the retry executes only its
  lanes and settles passed.

Release behaviour is unchanged by PR 1: `verification._candidate_results`
selects candidate-kind results only, so a retry result is invisible to the
release driver until PR 2.

## PR 2 — composed release evidence

`tools/release/batch_reference.py` gains schema
`lmdj.ci-batch-release-reference.v2`: the v1 fields of the primary candidate
run plus `retries`, each a v1-shaped record whose request is kind `retry`
with a focused selection and `retry_of`. `verification.terminal_result`
composes the unique candidate result with its retry result; a suite passes
when the primary passed it or the retry passed it; every suite must pass.
`batch_evidence._verify` verifies each run as today (completed attempt 1 of
the pinned workflow on main, retained attestations and bundles) and
re-proves the environmental class of the primary's non-passed suites from
the primary run's jobs API and requires each `failed` suite's frozen proof to
name exactly that suite's failing jobs in the retained verdict (the reducer
is pure and reference-opaque, so this exact-jobs check belongs to the
consumer); the primary executor's `failure` conclusion is accepted only
through those suites. `verified_recheck._verification`
rechecks every run of the composite. The intent, plan marker v3 and the
published audit bind the whole composite document, unchanged in code.
Governance: `docs/governance/version-management.md` §12.1,
`docs/design/2026-08-13-lmdj-standard-release-pipeline-design.md` §3 and the
lmdj-release skill record the rule and the operator command; a pitfall is
recorded if the first real use finds a trap.

Declared files: `tools/release/batch_reference.py`, `tools/release/batch_evidence.py`,
`tools/release/verification.py`, `tools/release/verified_recheck.py`,
`tools/release/carriers.py`, `tools/release/audit.py`, `scripts/ci/batch_verdict.py`
(a retry selection is canonical but not closed over the dependency graph; the
closure rule exists for changes, and a retry is not one), the governance,
design and skill documents above, this plan, and the tests
`release_batch_evidence_test`, `release_verification_carrier_test`,
`release_verified_recheck_test`, `release_model_test`,
`release_entry_enrollment_test`, `release_batch_binding_test`,
`release_skill_test`, `ci_batch_verdict_test`.

Lowest-tier tests and the defect each catches: the consumer accepts a
candidate composed with its environmental retry and refuses a lane that
failed on a test, a proof that does not name exactly the failing jobs, a
retry covering other suites, a retry that did not pass, a composite over a
passed candidate and a plain reference over a failed one; the carrier
composes a failed candidate with its passed retry into the v2 document and
the `;retry:<run>` reference string, and refuses a retry that does not cover
the failed suites; the recheck verifies both runs and treats drift of either
as conflict; the ledger model binds one retry of the same candidate and
target; prepare records the candidate executor's actual conclusion and the
marker and audit bind the composite.

## Version Management

Version impact: none for PR 1 (scheduler control plane only; no Product,
Module, Contract or Provider version changes, no Build allocation). PR 2
changes the release reference document schema that the intent ledger and
plan marker embed; the batch reference is not a registered `contracts/`
Contract, and v1 documents stay readable, so PR 2 records
`Version impact: none` with that reason unless its review finds otherwise.
PR 2 confirmed: `Version impact: none`.

## Documentation Impact

Documentation impact: none for PR 1. Reason: no page under
`apps/docs-site/docs/` describes the scheduler's request kinds; the plan and
decision live under `docs/`. PR 2 declares its own impact.
