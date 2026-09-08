# Portal snapshot projection across a main batch

## Scope

Declared files:

- `.github/workflows/ci.yml`
- `.github/workflows/architecture-portal.yml`
- `apps/architecture-portal/scripts/check-snapshot-projection.mjs`
- `apps/architecture-portal/test/snapshot-projection.test.mjs`
- `tests/build/ci_batch_execution_workflow_test.py`
- `docs/plans/2026-09-08-lmdj-ci-portal-snapshot-interval.md`

Run `34188723712`, job `101949146999`, supplied `fe043fd3` to `4eb6a139`
to the PR own-tree projection checker. Build 1.0.44.0's introducing commit
`966a9957` matches its recorded projection exactly; the latest target differs
only in two subsequently updated mutable operations pages. The failure is a
range-semantics defect, not permission to rewrite immutable metadata.

Default PR mode keeps the strict own-tree rule. An explicit main interval mode
is selected only from the existing authenticated self-test preparation output.
It requires exact available commits, complete history and first-parent base
membership, and checks every metadata addition against its introducing tree,
including additions later removed or repaired. Unknown modes fail closed.
The caller still checks out the exact target and runs the complete Portal
verification; no lane, permission, threshold or immutable asset is changed.

Empty main intervals (including full candidate base equal to target) explicitly
report no introductions, not candidate validation, and do not invent a HEAD^
delta. The unconditional full Portal command still runs canonical current
Product Build provenance at the checked-out exact target. The interval checker
does not acquire release-audit responsibilities. Git topology checks cannot
authenticate GitHub identities; the existing claim/source-authenticated caller
owns that authority and alone selects this mode.

## Verification

Lowest tier: real Git fixtures through the checker API/CLI, including two
snapshots across multiple commits, bad introduction followed by a repair,
strict PR divergence, invalid mode/ref/history, and empty candidate interval.
Keep all existing projection tests. Run the workflow contracts, staged
ownership, full CI contracts with explicit actionlint/ShellCheck, the actual
historical red/green range, and the complete Portal check with locked npm deps.
Local evidence does not turn the historical failed job into a pass or prove
the next hosted batch. No release audit, snapshot creation or remote mutation.

Implementation review tightened missing-object handling: a first-parent addition
must have readable metadata at that commit. The original PR-only deletion
compatibility cannot turn an unavailable main metadata blob into a skipped
check. A real Git fixture removes its precise loose blob and verifies rejection.

Recorded verification:

- 16 projection tests pass, including all existing PR tests and real Git legs.
- 30 execution/workflow contracts pass, preserving candidate provenance for
  empty intervals and binding main mode to the existing authenticated output.
- Actual `fe043fd3` to `4eb6a139`: default own-tree mode reproduces the hosted
  failure; main-interval mode passes exactly one introduction, `966a9957`.
- Full CI contracts pass: 1705 tests, no skips, 46.593 seconds, pinned
  actionlint 1.7.12 and explicit ShellCheck 0.9.0. The initial run detected a
  legacy typed-input ordering assertion; the new optional input now follows
  the existing inputs without modifying that assertion or their semantics.
- Changed workflows pass actionlint with explicit ShellCheck; only the known
  `concurrency.queue` parser compatibility warning is ignored.
- Final stable-tree complete Portal check passes: 74 tests, 39 current pages,
  10 diagram sources/20 outputs, canonical current-Build provenance, typecheck,
  production build, 42 routes and internal links. Locked npm dependencies were
  installed without changing the lockfile. The earlier complete run also
  passed but is not substituted for this final-tree evidence.
- Staged ownership passes all 66 tests; staged whitespace check passes.

Logs: `/tmp/lmdj-portal-interval-{target,workflow,real-red,real-green,ci-final,actionlint,portal,portal-final}.log`.

## Version Management

Version impact: none — correct the CI comparison tree without changing any
Product, Assembly, Contract, snapshot or release identity.

## Documentation Impact

Documentation impact: none — existing pages already require provenance against
the introducing commit, not future mutable pages. This internal checker repair
restores that documented invariant without changing operator commands or
release authority. Portal tooling changes require the complete Portal check.

## Pitfall Impact

Pitfall impact: none — the directly reproducible checker range defect is
fully captured by its real Git regression; preserve existing provenance and
fail-closed diagnostic guidance.

Local implementation and review only; root owns subsequent shipping.
