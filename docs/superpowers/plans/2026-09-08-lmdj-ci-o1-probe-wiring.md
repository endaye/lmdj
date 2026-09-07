# Manual O1 recovery probe wiring

Delivery revision: the reviewed four-file delta from
`8b81b21de1c00ead3e036bddf50793f0a14e39d0` is now applied independently on
main `e7fb23cc7f0156327730d88d0fc112a0fa5a2383`, where the actual probe
dependency is already merged. Original stacked verification and HOLD notes
below record that earlier development stage, not the current integration state.
The workflow and both test files remain byte-identical to the reviewed version;
no legacy reporter behavior or automatic trigger is changed by this delivery.

## Declared Task files and dependency

Change `.github/workflows/self-test-report.yml`, add
`tests/build/ci_o1_probe_workflow_test.py`, update the exact scheduler/artifact
exclusion assertions in `tests/build/ci_batch_runtime_workflow_test.py`, and
add this plan. No other workflow, controller or probe module changes.

Depends on the separately reviewed `scripts/ci/o1_recovery_probe.py`; do not
copy it into this Task. Its real CLI takes required `--config`, `--request`,
`--root`, `--summary`, without an action subcommand or output argument. The
closed intent defaults fault injection to disabled; actual authorized successful
POST-response suppression exits 86 and must leave the workflow visibly failed.

## Implementation and safety

Add only manual `batch_operation=recovery-probe` and a dedicated `probe_request`
string input. Config is the existing `report_config` isolated scheduler/outbox
pair, not the normal scheduler config. Execute within the existing exact-main,
first-attempt controller job, shared short writer lock and existing permission
set. CLI independently authenticates and restricts isolated Issue identities.

Reject mixed scheduler, legacy and review inputs before invoking the CLI. JSON
travels as environment data to files, not inline source or shell interpolation.
The probe has no `GITHUB_OUTPUT` action/request/executor, does not upload a
controller result, and cannot select the heavy reusable executor. Existing
scheduler and reporter steps exclude this operation. Do not add continue-on-error
or turn exit 86 into success. Existing crons and automatic triggers stay unchanged.

## Verification and rollout boundary

Test the actual inline Python command boundary with hostile JSON strings,
missing/mixed inputs, disabled real CLI intent, ordinary failure and exit 86.
Validate real CLI flags, workflow guards, unchanged permissions/locks and no
execution output. Run affected workflow contracts, complete CI contracts with
pinned actionlint, staged ownership and final committed-range docs-static.
Attempt Portal check before commit; record missing dependencies without claiming
a build pass. No remote fault injection, Issue initialization, dispatch, or
product execution is performed by this Task.

Local tests run stacked on the actual dependency commit
`0e0c79f76ad37dfba5345fce799e4c24fa3261cd`, never copy production files or
silently skip the CLI compatibility leg. The existing report test extracts only
its own step, stopping at the next named or uses step; adding a probe step must
not conflate two independent run blocks.
Shipping is held until dependency integration and the current none O1 window
permit it; local protocol tests do not prove real response-loss recovery.

Local results: seven new probe-boundary tests and 1,462 complete CI contract
tests passed without skips, including the existing 19 rehearsal workflow tests.
Staged ownership: 66 passed. Pinned actionlint passed with only the pre-existing
`queue` concurrency key excluded from its older syntax parser. Portal check:
54 tests passed, three missing-dependency failures; downstream validation/build
did not run. The existing report-step extractor and lock count first failed
after introducing a third exclusive step, then passed with truthful step
boundaries and three uses of the same lock environment. No invariant was dropped.

Fresh-main delivery verification: seven probe-boundary and 19 existing workflow
tests passed; complete CI discovery passed 1,481 tests without skips. Staged
ownership passed 66 tests, cached whitespace passed, and actionlint retained
only the same exact `queue` syntax compatibility exemption. Portal again ran
57 tests: 54 passed and three failed for missing `glob`, `gray-matter` and
`cheerio`; no later build stages ran. Actual remote A/B fault/recovery journeys
remain unexercised by this Task.

## Documentation Impact

Documentation impact: none — internal manual-only controlled rehearsal entry;
no current automatic cutover, Portal page, diagram or product identity changes.

## Version Management

Version impact: none — CI diagnostic wiring only, no version allocation or
release operation.

Pitfall impact: none — preserve existing authenticated boundaries and explicit
whole-journey evidence; no new platform incident is inferred from local tests.
