# Controlled PR Review failure diagnosis — NEVER MERGE

Status: local controlled-rehearsal preparation, not a production repair.
Branch: `fix/ci-review-controlled-diagnostics`.
Base and every trusted review/publisher checkout:
`d360d3805f21a18ec75d86bb0fc69cda747e9d9d`.

## Scope and authority

Declared files:

- `.github/workflows/pr-review.yml`
- `scripts/ci/review_diagnostics.py`
- `tests/build/ci_review_diagnostics_test.py`
- `tests/build/ci_pr_review_workflow_test.py`
- this plan

This branch must NEVER MERGE. Root reviews, commits and explicitly controls any
push or dispatch; this implementation does not perform those operations. No
release, secrets/variables change, runner configuration change or model change
is authorized. Do not open an integration PR for this branch.

## Diagnostic boundary

Run `34133275617` initialized Claude 2.1.259 then returned `is_error=true`, one
turn, no model usage. The action raised missing structured output before showing
the upstream error. Existing public logs cannot establish whether authentication,
quota, model selection, transport or structured-output compatibility failed.
The workflow endpoint agrees with Z.AI documentation; the displayed model alias
alone is not proof of a model-routing defect.

Only the exact named branch gains a `workflow_dispatch` admission exception.
All five existing consumers use the trusted base above. Backend selection,
credentials, Claude args/model, Grok and publication validation are unchanged.
Only after Claude action failure, a separate sparse checkout of the exact
dispatch SHA supplies the new sanitizer, run in isolated Python mode. It emits
only a closed category/reason, integer HTTP status and validated job identity.
The fixed execution filename is size-bounded and must be a regular non-symlink
file. Missing/malformed/conflicting observations are unknown, not success.
API/model text is not authoritative; this is a diagnostic hint, never review
completion, source provenance, successful authentication or release evidence.

No full execution file upload, full model output, headers, arbitrary error
strings or exceptions are printed. Failure remains failure, and the normal
publisher still requires validated review output and exact current head.

## Verification and next step

Small sanitizer and CLI tests must cover real error envelopes, secrecy, missing
files, malformed/duplicate JSON, symlink/oversize inputs and invalid identity.
Run CI contracts and pinned actionlint; root may run portal validation before
its local commit. A passing local test does not establish a working backend.

Local verification completed: 8 sanitizer/CLI tests, 26 PR Review tests and the
full 847-test `ci_*_test.py` collection pass. `git diff --check` passes.
Actionlint 1.7.12 passed after checking the existing workflow's exact archive
SHA256, with only the existing precise `concurrency.queue` schema exception.
Root also completed the Portal check: 65 tests, 37 pages, diagrams, immutable
snapshot, typecheck, production build and 42 routes passed. Real diagnostic
dispatch and backend recovery remain separate, unverified steps at commit time.

After root review and separate push/dispatch, the operational command is
`gh workflow run pr-review.yml --ref fix/ci-review-controlled-diagnostics -f pr_number=NUMBER`.
It intentionally reuses the original selector and both reviewer jobs. Read
only the sanitizer category/status, then choose one concrete next diagnostic
or report an external authentication/quota blocker. Do not alter models and
credentials simultaneously or call this O1 success if no trusted publisher ran.

## Version Management

Version impact: none — temporary CI diagnostics change no product identity.

## Documentation impact

Documentation impact: none — this NEVER MERGE diagnostic branch changes no
production workflow or portal behavior. This plan records its temporary scope.
