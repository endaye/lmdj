# Preserve bounded Grok failure diagnostics

Relates to #819. The Grok fallback in run 34169838085 failed in about one
second, but its wrapper discarded every error boundary and printed only a
generic pipeline failure. The exact pinned Grok 1.0.13 executable locally
matches the CI SHA256 and accepts the complete invocation with `--help`, so
argument incompatibility is not established. No model request was sent.

## Task

Declared files:

- `scripts/ci/review_pipeline.py`
- `tests/build/ci_review_pipeline_test.py`
- this plan

On Grok failure, emit a single closed JSON diagnostic identifying the locally
observed failure boundary and actual exit code when a process completed.
Categories distinguish missing credentials, process launch, timeout, process
exit, malformed or error envelope, and invalid review. Do not emit raw output,
exception strings, prompts, credential contents, or arbitrary provider fields.
Missing credentials fail before process launch. Every failure remains a failed
review under the existing capture/fallback protocol. Add no workflow permission
or artifact contract and do not reinterpret an upstream error as success.

GLM remains a separate observation gap: its action logs missing structured
output, but the original HTTP/error detail is absent and the shared execution
file is overwritten by Kimi. This Task does not guess a provider cause or
copy the existing NEVER MERGE controlled diagnostics into production.

Baseline: 22 pipeline tests pass. Lowest-tier checks: pipeline tests exercising
real CLI error output through bounded process doubles, absence of sentinel
secrets and raw text, cleanup on each failure, existing scope tests, and
staged-index ownership. Test composition with the separate label-schema commit
in a disposable directory. No new required CI gate is introduced.

## Version Management

Version impact: none — diagnostic output does not alter product, module,
provider, or Contract identity.

## Documentation impact

Documentation impact: none — this improves failure observability within the
existing review protocol and changes no portal-facing behavior.

## Pitfall disposition

The finite diagnostic and secrecy invariant is fully represented by regression
tests; no extra process-ledger entry is needed.

## Acceptance boundary

A local pass proves safe failure classification, not restored backend service.
A real authenticated current-head review and publication remain unverified.
Push, PR, dispatch, issue writes, and configuration changes are not authorized.

## Verification results

- Pipeline: 30 tests passed; scope: 36 tests passed.
- Staged-index ownership: 66 tests passed. Staged whitespace check passed.
- Both patches apply sequentially without conflicts to an archive of their
  common `origin/main` base. In that combined tree, pipeline 33, scope 36 and
  PR Review workflow 28 tests passed with actionlint 1.7.12 available.
- Independent root review found no blocking issues in implementation, tests,
  secrecy or exact temporary-auth cleanup. No real backend run was performed.
