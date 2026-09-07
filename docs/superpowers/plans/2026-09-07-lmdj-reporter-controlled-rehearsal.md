# Temporary controlled reporter rehearsal

Status: first remote drill failed; repaired exact-commit repeat pending.
Base: `d360d3805f21a18ec75d86bb0fc69cda747e9d9d`.
Branch: `feat/ci-report-controlled-rehearsal`. NEVER merge this branch into main.

## Task and declared files

User authorized a controlled self-test/report drill before the O2 protection
cutover. This Task prepares only the reporter transport leg. Root reviews the
exact diff and separately controls commit/push/dispatch; no PR/merge is needed
or allowed for this temporary branch. Live required checks, production tests,
release candidates, publication and deployment are untouched.

- `.github/workflows/self-test-report.yml`
- `scripts/ci/self_test_report_rehearsal.py`
- `scripts/ci/hosted_runner_policy.json`
- `tests/build/ci_self_test_report_rehearsal_test.py`
- `tests/build/ci_self_test_report_workflow_test.py`
- `docs/superpowers/plans/2026-09-07-lmdj-reporter-controlled-rehearsal.md`

The harness prefix already matches the CI full rule; tests/build/ci_ and plans
already have explicit ownership. The hosted allowance is branch-only and names
the authority reason; no runner or physical-host setting changes.

## Protocol and far-side observations

Dispatch the already registered Self-test Report workflow on this exact short
branch with `rehearsal_only=true`, `run_id=0`, `reconcile=false`. Its production
report job is skipped, and a separate rehearsal job additionally requires this
branch name and attempt 1. It uses the normal reporter concurrency lock; this
short bounded drill may briefly delay another report, but cannot replace or
cancel it. No schedule or workflow_run event selects the rehearsal job.

Checkout reviewed reporter fix `d890a593d5882f2cfe947746adc8623b2b838e3c`, and the
reviewed harness at this dispatch's exact github.sha into separate paths with
persist-credentials disabled. The genuine Actions GITHUB_TOKEN gets only
contents:read and issues:write. No token is retrieved from a local gh session,
exported to local infrastructure, printed, or used by a product workload.

Use a fresh random 12-hex label/key namespace and record the actual rehearsal
run id/attempt in observations. Labels never include production `self-test`;
all body/title/label/key ownership checks precede existing-issue writes.
The real apply_report, retry loop and github-actions[bot]/Bot author checks
are unchanged; no API response author is rewritten. Inputs are synthetic
Report objects, not fabricated verdicts, target identities or test results.

1. First report creates exactly one isolated Issue; 0 comments.
2. Same observation returns duplicate with no writes.
3. New observation comments on the same Issue; close it then recur to verify
   real reopen and a second comment.
4. Inject 403 locally BEFORE HTTP POST; original reporter raises, does not
   retry or write, and persisted comments remain 2. This is not a real GitHub
   permission-denial measurement.
5. Retry explicitly; a third comment appears. Repeat adds nothing.
6. Persist a real fourth comment, locally discard its success response and
   raise transport error. Fixed reporter read-only reconciliation reads GitHub, returns
   duplicate, and comments remain exactly 4.
7. A second isolated bucket repeats lost-response recovery for issue creation.
   Exactly two issues exist, and each observation marker appears exactly once.
8. Finally close both isolated Issues and independently retry cleanup in an
   always step. Re-read to verify closed; never delete issues or labels.

Every step emits bounded credential-free JSONL. Retain it as
reporter-rehearsal-RUN-ATTEMPT plus the step summary, explicitly separate from
self-test verdict/skip artifacts. A run failure or missing assertion remains
a failure; no synthetic success check is posted and no production verdict is
created or changed. Genuine API failures remain distinct from injected ones.

## Stop, recovery and retirement

Stop on wrong source digest, context/run/attempt mismatch, unexpected author,
namespace collision, unsafe issue ownership, API failure or any count/marker
assertion. Never relax marker trust to make a PAT pass. If cleanup fails or a
job is terminated before cleanup, retain the exact logged label/run/issue ids;
root verifies body/title/label ownership and closes only those Issues. No broad
issue sweep. A failed job rerun is refused; use a fresh dispatch/random namespace.
After remote evidence is recorded and isolated issues are confirmed closed,
root may retire this temporary branch/worktree under separate cleanup authority.
The label remains as auditable history. This code is never merged to main.

## Verification

Run python3 -S for the new harness tests and all ci_* tests, and pinned actionlint
(only the pre-existing exact concurrency queue schema exception). Stage only
declared files, run ownership after staging and inspect cached diff/check.
Local mocks verify harness safety but do not count as real API acceptance.
No product/native build is part of this temporary remote-only drill. Root also
ran the existing pre-commit Portal check: all 65 tests, 37 pages, diagram and
immutable snapshot validation, typecheck, production build and 42 routes passed.
Root owns the subsequent commit/push and authorized branch dispatch.

Local results: python3 -S all CI contracts 847/847; standalone harness 8/8 and
reporter workflow 10/10; staged ownership 66/66; pinned actionlint and cached
whitespace check pass. One combined-test mock identity leak initially issued
read-only repository GETs using a fixed invalid test token (HTTP 401, no writes).
The test now pins its imported module and denies real socket connections;
the complete rerun passed. No live drill acceptance is claimed.

## First live discovery and repeat

Run 34134692783 failed: an immediate negative label-filtered list after a
successful real bot POST caused duplicate issues 771/772. Initial cleanup also
mistook an empty list for closure. Root verified exact ownership and closed
both at 14:47:06Z/14:47:10Z. Cache versus replication/index delay is unknown.
The failed record is retained; it is not passing acceptance.

The repeat pins the independently reviewed production fix above (also
cherry-picked into this never-merged branch for source-identical local tests).
The adapter tracks attempted POST count and known created IDs. Cleanup unions
known IDs with label discovery, checks exact ownership and closure by direct
GET, and refuses to claim cleanup when any attempted POST lacks a known issue.
An always-step JSONL journal preserves that knowledge across cleanup processes.
This does not guarantee recovery from an unlogged crash or unknown remote ID.
Use a new dispatch/namespace, never rerun attempt 2.

## Version Management

Version impact: none — temporary reporting transport harness changes no product,
module, provider, contract, build, tag or release identity.

## Documentation impact

Documentation impact: none — never-merged operator rehearsal only; no current
portal page, diagram, projected identity or product behavior changes.

Pitfall impact: none — bot marker-author trust is directly in reporter code;
the harness tests pin it and distinguish real persistence from injected faults.
