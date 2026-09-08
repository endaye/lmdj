# Constrain review advice to active policy labels

Relates to #819. The Kimi action in PR #855 run 34169838085 returned
`creator`, `docs_static`, and `portal` without the required `test:` prefix.
The trusted validator correctly rejected the output. Both Claude prompts point
at policy suite IDs while their JSON schemas accept arbitrary strings.

## Task

Generate the Claude response schema from trusted active policy, constrain label
items to its complete `test:` vocabulary, and pass the same schema to both
Claude backends. Give explicit prefixed examples in both prompts. Preserve the
closed validator, fallback order, deterministic scope floor and publication
checks. Unknown and bare labels must still fail; do not normalize model data.

Declared files:

- `.github/workflows/pr-review.yml`
- `scripts/ci/review_pipeline.py`
- `tests/build/ci_review_pipeline_test.py`
- this plan

Lowest-tier checks: review pipeline and scope unit tests, PR review workflow
contracts, and staged-index ownership check. Exercise schema delivery from the
trusted collection step into both action arguments, legal labels (including
`test:none` and `test:full`), and the observed bare-label rejection. Check the
workflow with actionlint when available. No new required CI gate is added.

Baseline: 22 review pipeline tests pass before changes. The backend incident
is still open: this local repair addresses malformed label generation, not
GLM's missing structured output or Grok's opaque process failure. A successful
real current-head backend run and authenticated publication remain unverified;
no push, PR, dispatch, remote configuration change or issue mutation is part
of this Task. The existing NEVER MERGE controlled-diagnostics worktree is
separate and must remain untouched.

## Version Management

Version impact: none — review schema generation changes no product, module,
provider or Contract identity.

## Documentation impact

Documentation impact: none — this repairs review output constraints to match
the existing documented policy, with no portal-facing behavior change.

## Pitfall disposition

The defect and its invariant are fully captured by the schema/validator
regression tests; no additional process-ledger entry is needed.

## Verification results

- Review pipeline: 25 tests passed; review scope: 36 tests passed.
- CI contract collection: 1,644 tests run, 1,643 passed and one actionlint
  availability check skipped. The PR review contract was then rerun with actionlint 1.7.12 available:
  all 28 tests passed, including the previously skipped parser check.
- actionlint 1.7.12 accepted the changed PR Review workflow.
- Staged-index ownership: all 66 tests passed, including full tracked-path
  ownership. `git diff --cached --check` passed.
- No real backend request, publication or service recovery was exercised.
