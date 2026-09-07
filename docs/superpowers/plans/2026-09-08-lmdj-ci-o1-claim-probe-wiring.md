# O1 C1 manual workflow wiring

Status: local implementation awaiting exact-head review. No push, remote
dispatch, cancellation, initialization or release belongs to this Task.

## Dependencies and declared files

The original development stack started from reviewed A/B wiring
`8b81b21de1c00ead3e036bddf50793f0a14e39d0`, including its response adapter and
design. Reviewed storage manifest `ca668cc0056deb60bf23b7a699fcfad23d623eca`,
the two C1 design commits, and reviewed C1 adapter
`f68f966a300c082503e24db1e0f0f19bda1c488a` are retained as separate dependency
commits in that stack, not rewritten or folded into that wiring implementation.
The standalone delivery is based on actual main
`ba9fd223ca35135dfd2cb4523d33e956ce3d1a8a`, which already contains the fixed
manifest, A/B adapter/wiring and C1 adapter. It contains only the four declared
file changes below, not any dependency or earlier design commit. Its workflow
and both test blobs are identical to reviewed
`191b9338b379be39c1b8b7092aa5b1a6ceafffdb`; only this delivery record is updated.

Declared files:

- `.github/workflows/self-test-report.yml`
- `tests/build/ci_batch_runtime_workflow_test.py` — only update the existing
  exact scheduler/artifact exclusion assertions and short-lock sentinel count
  to include the fourth, mutually exclusive controller operation family.
- `tests/build/ci_o1_claim_probe_workflow_test.py` — new actual-entry journeys.
- This plan.

No shared manifest, adapter, Runtime, reducer, A/B tests or reporter is changed.
The existing legacy schedule/workflow_run triggers and reporter body, A/B
probe step, reusable executor and all existing permissions remain unchanged.

## One manual route, no executable bridge

Add `claim-probe` to the existing `batch_operation` choices; the default remains
legacy. The same `Incremental batch controller` job requires manual current
main and actual first attempt. It retains the existing short job-level
`self-test-report` lock, cancel-in-progress false, and
contents:read/actions:read/issues:write; no parent lock or new permissions.

Use existing `journal_config` for the fixed manifest claim role and existing
`probe_request` for the closed C1 intent. The actual adapter independently reads
the reviewed fixed-path current-control Git manifest and checks complete config
equality. The workflow accepts no arbitrary manifest path or role override.
Missing config/intent or mixed legacy/report/scheduler parameters fail before
the CLI. Intent without its fault field remains disabled; there is no default
enabled fault and no automatic C1 trigger.

The independent C1 step writes exact JSON input bytes to its own temporary
directory, then invokes the real adapter with only `--config`, `--request`,
`--root` and `--summary`. Its actual process status is propagated: 87 is a
controlled claim-before-output exit, 1 an ordinary failure, and 0 the disabled
path. No success claim is inferred solely from a subprocess exit status.

Both the ordinary control step and its result artifact explicitly exclude
claim-probe. Report steps remain report-prefix-only and A/B remains exactly
recovery-probe. C1 is placed before the unchanged A/B step. No C1 step output,
result file, execute artifact, continue-on-error or output reader is added.
The reusable heavy job still consumes only `steps.control` outputs, which C1
cannot produce even if its subprocess accidentally returns success.

## Lowest-tier verification and far-side journey

The new workflow suite extracts and executes the actual embedded Python, checks
exact CLI argv and on-disk config/request bytes, and invokes the real adapter.
Its enabled journey uses complete real Runtime/journal/Git/manifest fixtures:
workflow input → actual C1 main → durable observe/admit/full claim → exit 87
and honest summary → no GITHUB_OUTPUT/result file → distinct ordinary settle
with 16 missing debts → another fresh ordinary replay with unchanged state.
The original lost-claim-response journey exits 1, retains honest error semantics
and never logs credential text or claims a controlled success. Disabled,
mixed/missing inputs and accidental subprocess success also produce no
executable output. These are local fixtures, not hosted acceptance evidence.

Required Task commands: new workflow suite; existing runtime workflow and A/B
workflow suites; complete CI discovery with pinned actionlint; direct workflow
actionlint with only the known existing queue-key compatibility exemption;
staged ownership and whitespace. Precommit Portal results are recorded honestly.

Remote prerequisites remain separately authorized shipping and exact-current
main verification of all dependencies. A real C1 dispatch may run only in the
controlled window after genuine old executions are terminal. Real A/B recovery,
hosted lock/permissions and C1 fault/recovery acceptance are not certified here.
C2 actual GitHub cancellation remains unimplemented and separately authorized.

## Version Management

Version impact: none — internal diagnostic workflow route; no product, module,
provider or Contract identity changes.

## Documentation Impact

Documentation impact: none — internal workflow and plan, no Architecture Portal
pages or projected product facts change.

Pitfall impact: none — applies existing complete-journey and strict external
fixture guidance; no new remote incident or hosted fault was observed.

## Original stack verification results

- New actual-entry suite: 9 passed; existing Runtime workflow suite: 19 passed;
  existing A/B workflow suite: 7 passed.
- Full CI discovery on the combined reviewed dependency stack: 1502 passed,
  no skips, with pinned actionlint configured.
- Direct actionlint passed, ignoring only the exact pre-existing `queue` key
  compatibility diagnostic; no new ignored category or workflow permission.
- Staged new-file ownership: 66 passed; staged whitespace passed.
- Precommit `scripts/architecture-portal.sh check`: exit 1, initial Node tests
  57 total / 54 passed / 3 missing-dependency failures (`glob`, `gray-matter`,
  `cheerio`), no skips. Later Portal stages were not reached; no Portal pass
  or dependency repair is claimed.

No push, Issue mutation, initialization, dispatch, cancellation or release was
performed in this implementation Task. Platform execution remains on hold for
root's independent exact-head review and separately authorized controlled window.

## Standalone delivery verification

On the main-based standalone worktree, the actual-entry 9 tests, existing
Runtime-workflow 19 tests and A/B-workflow 7 tests all passed again. Complete
CI discovery with pinned actionlint passed 1514 tests, no skips. Direct
actionlint retained only the same exact pre-existing queue-key exemption.
Staged new-file ownership passed 66 tests and staged whitespace passed.
Precommit Portal was actually rerun: exit 1, 57 initial Node tests / 54 passed /
3 missing-package failures (`glob`, `gray-matter`, `cheerio`), no later Portal
stages reached and no Portal pass claimed. Only local preparation is complete;
no push or merge is performed during root's active A/B rehearsal window.
