# Preserve the PR Review run title through YAML parsing

## Task

Branch: `fix/ci-review-run-title`, isolated from `origin/main`
`a9481bdf38a0c34826f8718fef70b884d0f673f7` (Product Sound Set PR #768).
One Task: quote the complete `run-name` scalar and cover its real parsing.

Declared files:

- `.github/workflows/pr-review.yml`
- `tests/build/ci_pr_review_workflow_test.py`
- this plan

## Evidence and boundary

The unquoted `run-name: PR Review / #...` starts a YAML comment after the slash,
silently removing both PR and head expressions. Read-only GitHub API evidence
for run `34133275617` shows `name` and `display_title` both `PR Review /`, while
`pull_requests` identifies PR #765. The liveness collector expects the complete
`PR Review / #NUMBER @ ...` display title and drops the truncated record.

Quoting preserves the original expressions without changing selection,
credentials, model, trigger/admission, publication permissions or merge policy.
Historical truncated run titles do not change and are not reconstructed by
this Task. This fix does not establish backend health: the independent GLM 429,
Grok authentication failure and TSan host prerequisite failure remain separate.

## Verification

The regression uses pinned actionlint's real YAML and expression parser. It
substitutes forbidden run-name contexts as probes for both expressions: the
old unquoted scalar silently discards them, whereas the quoted scalar exposes
both to semantic validation. The test fails before the quote fix (0 parsed
expressions instead of 2) and must pass after it. This deliberately avoids
adding PyYAML or implementing a competing YAML parser.

Find actionlint through `LMDJ_ACTIONLINT`, PATH, or the existing CI installation
in `RUNNER_TEMP`. Tool-free stdlib-only discovery skips this one parser test;
the Task-specific verification supplies the pinned executable explicitly and
must not claim the semantic test passed when it skipped.

Run the PR Review tests with the pinned tool, the full CI contract suite,
pinned actionlint and diff/ownership checks. Root reviews and controls shipping;
no remote mutation is performed by this implementation agent.

Local results: PR Review 27 tests and the full 840-test CI contract suite passed
with actionlint 1.7.12 supplied explicitly (no parser-test skip). Full workflow
lint passed with only the existing precise `concurrency.queue` exception.
Tool-free PR Review discovery also passed with its one explicit parser-test
skip; no new dependency or unexpected tool-free failure was introduced.

## Version Management

Version impact: none — workflow title parsing changes no product identity.

## Documentation impact

Documentation impact: none — the intended existing review title and liveness
behavior are restored; no user-facing workflow or portal procedure changes.
