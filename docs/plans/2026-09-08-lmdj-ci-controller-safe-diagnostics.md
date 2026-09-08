# Safe controller failure diagnostics

## Task and declared files

One internal diagnostic Task, originally based on
`338cbe5d51ff1ea9960682e247fea396fc0ab662`, finally migrated without
implementation changes to `aaeee6fe6147bf3f96583f92bef7f1b2418f5a4d`:

- `scripts/ci/incremental_entry.py`
- `scripts/ci/batch_runtime.py`
- `tests/build/ci_incremental_entry_test.py`
- `tests/build/ci_batch_runtime_test.py`
- `docs/plans/2026-09-08-lmdj-ci-controller-safe-diagnostics.md`
- `.agents/pitfalls/gate-failure-readability.md` (existing recurrence)

Actual schedule [34199071822](https://github.com/endaye/lmdj/actions/runs/34199071822)
failed before source witness and produced only the generic failure message.
This Task makes that failure phase visible; it does not identify or repair the
underlying production failure and is not O2 acceptance evidence.

## Design

Emit a separate closed `lmdj.ci-entry-diagnostic.v1` JSON log with only schema,
operation (`control`, `reports`, `unknown`), allowlisted stage and typed error
category. Never serialize exception text, class names, causes, HTTP bodies,
Git stderr, raw events, credentials or unverified source hints. Unknown values
become `unknown`. Existing generic why/remedy and all exit/result semantics stay.
Authentication substage is cleared only after successful authentication, not
in a failure finally block. Later event, journal and report errors must not be
misattributed to the last successful authentication check.

An optional closed `http` numeric summary inspects at most four exact known
exception wrappers through context, with cycle detection. Only exact HTTPError
status integers 100–599 and single ASCII decimal HTTPMessage headers (remaining,
reset, retry-after; at most 12 digits) survive. Unknown wrappers, duplicates,
negative/malformed values, arbitrary header maps and all other fields are
omitted. No context text is rendered. This may help distinguish a future quota
response; it does not establish that quota caused the existing failure.

The line is not a source witness, execution authority, result or new gate.
No workflow, permissions, locks, API operations, queue/state, retries, product
coverage, storage identity or report payload changes are authorized.

## Verification

First reproduce missing stage at the real Entry CLI boundary, then cover each
Runtime authentication phase and successful clearing, later event/journal
failure, both operations and internal report catches, poisoned exception text,
class names and stage values. Run targeted suites, full CI contracts with the
existing pinned linters, staged ownership and nonempty committed docs range.
Actual local results:

- Missing-diagnostic CLI regression failed with `[]` instead of the closed
  phase record before implementation, then passed without execution output.
- Entry 38 tests and Runtime 63 tests passed, including real exception-context
  wrapping through both CLI operations and successful-authentication clearing.
- Staged ownership 66 tests and staged whitespace checks passed.
- Full CI contracts ran 1785 tests without skips; one unrelated baseline error
  remained in the workflow event-graph test's Python parsing of legal YAML
  `[Cloudflare Preview Build]`. It is not a diagnostic regression or a full pass;
  a separate Task owns its repair. Two final additional Entry journeys passed
  in the targeted 38-test run after that full run.
- After the independent parser repair, 1802 tests exposed one separate
  docs-site rename omission in an existing pitfall gate pointer. PR #943
  repaired that pointer independently; neither repair is part of this Task.
- On final base `aaeee6fe`, full CI contracts passed all 1802 tests without
  skips (41.637 seconds); Entry 38, Runtime 63 and staged ownership 66 passed
  again, as did explicit actionlint plus ShellCheck with the same exception.
  Final logs are `/tmp/lmdj-safe-diag-final-base-{full,entry,runtime,ownership,lint}.log`.
- actionlint 1.7.12 with explicit ShellCheck 0.9 passed using only the existing
  exact `unexpected key "queue" for "concurrency" section` schema exception.
- Nonempty committed-range `docs_static` passed against final base `aaeee6fe`;
  log: `/tmp/lmdj-safe-diag-docs-static.log`.

Logs: `/tmp/lmdj-safe-diag-entry.log`, `/tmp/lmdj-safe-diag-runtime.log`,
`/tmp/lmdj-safe-diag-full-final.log`, `/tmp/lmdj-safe-diag-ownership.log`.
No remote exercise is part of this Task; root reviews the uncommitted checkpoint
before local commit. No production cause or O2 completion is claimed.
The local environment has PyYAML installed. These local checks do not prove
dependency availability or a complete green run on a GitHub-hosted runner.
Both named migration stashes are retained; no worktree or branch was removed.

## Version Management

Version impact: none
Reason: internal controller diagnostics change no Product, Module, Contract,
Provider, Assembly, snapshot or release identity. No release operation.

## Documentation Impact

Documentation impact: none
Reason: only internal failure observability changes, not documented scheduling,
authentication, evidence or product behavior; no Portal page or diagram changes.
Portal rebuild is not applicable to this internal-only Task.
