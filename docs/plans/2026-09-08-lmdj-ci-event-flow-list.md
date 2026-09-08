# Parse explicit YAML workflow-name lists in the event graph contract

## Task and declared files

- `tests/build/ci_workflow_event_graph_test.py`
- `docs/plans/2026-09-08-lmdj-ci-event-flow-list.md`

Baseline `42261f2947f585848e52e8c7833d7e1f028b0842` reproduces one error in
seven event-graph tests: the legal `[Cloudflare Preview Build]` subscription
is passed to Python `ast.literal_eval`. `/tmp/lmdj-event-flow-baseline.log`
retains the red result. The Cloudflare workflow itself requires no change.

Replace that interpretation with a bounded explicit string subset, not a
general YAML parser: plain names, YAML single-quoted names (doubled apostrophe),
JSON-compatible YAML double-quoted names, and their comma-separated flow lists.
Own names and subscriptions share the same scalar decoder. Reject unsupported
syntax, nested structures, non-string scalars, malformed separators and empty
subscriptions with why/remedy rather than silently missing a graph edge.
Existing exact self-subscription checks and cross-subscription treatment remain.
No dependency, workflow, permission or trigger changes are authorized here.

## Verification

Preserve the actual-workflow red-to-green regression. Add quoted/unquoted/mixed
flow names, quoted commas, doubled apostrophes, exact own-name matching,
empty/invalid/nested/scalar negatives. Run targeted event graph tests, full CI
contracts with actionlint 1.7.12 and ShellCheck 0.9.0 explicitly available,
staged ownership and uncached docs_static before committing.

Actual results:

- `python3 tests/build/ci_workflow_event_graph_test.py`: 11 passed,
  `/tmp/lmdj-event-flow-target.log`; includes the unchanged actual-workflow
  test that failed on the baseline.
- `PATH=/tmp/lmdj-shellcheck-lint.cxa20X/extracted/usr/bin:$PATH LMDJ_ACTIONLINT=/tmp/lmdj-t2-shipping.MTX7q1/actionlint python3 -m unittest discover -s tests/build -p 'ci_*test.py'`:
  1782 passed in 37.669 seconds, zero skips, `/tmp/lmdj-event-flow-ci.log`.
  The explicit executables are actionlint 1.7.12 and ShellCheck 0.9.0.
- After staging both files, `python3 tests/build/ci_change_scope_test.py`:
  66 passed, `/tmp/lmdj-event-flow-ownership.log`.
- `scripts/local-ci.sh --base-ref origin/main --lanes docs_static --no-cache --json`:
  pass without cache, `/tmp/lmdj-event-flow-docs.json`.
- `git diff --cached --check`: passed. No workflow or production code changed.

## Version Management

Version impact: none — this is a test parser repair with no product or release
identity changes.

## Documentation Impact

Documentation impact: none — only an internal test parser changes, not operator
workflow, Portal pages, diagrams, tooling or projected identities.

## Pitfall disposition

Pitfall impact: none — the misuse of a Python parser for this YAML field is
directly derivable from the test and captured by the actual-workflow regression.
This test does not claim full YAML conformance or GitHub platform activation.
