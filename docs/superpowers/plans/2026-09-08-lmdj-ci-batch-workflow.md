# T4f — Reuse the real Core CI jobs for scoped batches

Depends on merged T4c `cbffd5d5013c5f05c5a5916fa6e25e489fe087af` and T4d's
`batch_execution.py`. This Task adds an inert callable entry; it does not enable
main push testing, delete daily testing, initialize journal state or release.

## Declared files

- `.github/workflows/ci.yml`
- `scripts/ci/hosted_runner_policy.json`
- `tests/build/ci_batch_execution_workflow_test.py`
- `tests/build/ci_self_test_workflow_test.py`
- `tests/build/ci_workflow_topology_test.py`
- `tests/build/ci_merge_queue_workflow_test.py` (retain native-only artifact condition).
- This plan.

## Implementation

Add `workflow_call` to existing Core CI, requiring `batch_request` and
`batch_executor` JSON. The trusted calling controller must already have durably
admitted/claimed that exact request for its own fresh attempt-1 run. Inputs alone
do not create authority. The caller passes only contents/actions read permissions
and, optionally, the already-existing runner-read secret by explicit name; never
`secrets: inherit`, issue write, review credentials or new permission scopes.

The reusable workflow inherits the caller's GitHub context, including its event
name. Entry resolution therefore compares `github.workflow_ref` with the native
Core CI ref and also observes both batch inputs. A called entry with two empty,
one missing, malformed, duplicated or wrong-run inputs fails; it cannot fall
through to the old empty-dispatch full path. Only an explicitly resolved native
entry may execute the old resolver/classifier and produce old evidence.

The current trusted checkout runs T4d `batch_execution.prepare`. A separate
checkout contains the frozen historical control's Git objects and three JSON
policies; no historical Python or control action is executed. Preparation uses
a detached data worktree sharing the initial checkout's objects, avoiding a
second full network clone under the unchanged three-minute control budget.
Complete actual main is fetched into that shared object store, and
T4d verifies commit types, ancestry, first-parent interval and executor identity.
This separates the current safe parser from older request policy data.

Prepared `lanes` drive the existing 14 lane guards; `suites` separately drive
TSan and Release stress. Existing product jobs retain their exact commands,
timeout budgets, resource locks, fixtures, coverage checks and macOS fallback.
The `core_macos` suite includes both Proof and native ASan by authoritative policy;
it is not silently split. The fixed-target outputs are shared with existing
checkout/HEAD assertions. Legacy pre-heavy/PR gates do not judge new batch data;
selected independent suites continue after unrelated selected-suite failure.

Only the new `Scoped batch verdict` producer emits the new evidence schema.
It reads raw `toJSON(needs)` including reusable TSan's existing infrastructure
output, then calls current T4d `from_needs` and T4a's full-policy aggregator.
No subset legacy policy is fabricated. All 16 suites remain represented;
unselected is not-selected and none is not-required, never a full pass.

Native daily/manual full request, scope, verdict and release evidence stay on
their existing path, guarded by explicit nonbatch mode. New full/focused/none
artifacts never use `ci-scope-*` or `self-test-verdict-*` names. No release
consumer is broadened. T5 alone will retire daily triggers after O1 acceptance.

## Runtime interface

Caller display name: `Execute incremental batch` (future O1 caller).
Producer job display name: `Scoped batch verdict`.
Artifact: `batch-verdict-<target_sha>-<run_id>-<run_attempt>`.
Exactly three files: `execution.json` (unaltered T4d prepare output), `needs.json`
(raw needs), `verdict.json` (T4a schema with original observations).

Producer business failure remains visibly red **after** upload. Reporter must
authenticate the exact source/run/attempt and these step conclusions:

- `Judge selected suites from actual needs`: success.
- `Retain scoped verdict and raw needs`: success.
- `Keep failed selected work visible`: failure iff recomputed verdict is failed;
  otherwise skipped. Producer overall success/failure follows that business
  result; canceled, timed-out, missing/failed upload is not ready evidence.

Ready evidence still requires whole executor-run terminal proof, not merely
producer/controller completion. Reporter recomputes T4d from raw needs using
trusted constants, not artifact-provided aliases/dependencies:

```python
aliases = {'core-tsan': 'nightly-tsan', 'core-stress': 'nightly-stress'}
dependencies = {job: ['change-scope'] for job in policy.inventory.job_owner}
dependencies['macos-primary'] = ['change-scope', 'select-macos-runner']
dependencies['macos-fallback'] = ['change-scope', 'select-macos-runner', 'macos-primary']
dependencies['core-macos'] = ['change-scope', 'select-macos-runner']
dependencies['core-asan-macos'] = ['change-scope', 'select-macos-runner']
```

Legacy pre-heavy and product predecessor ordering is not a semantic prerequisite
for this path; do not blame their intentional skipped state for selected work.
The trusted full policy still owns macOS alternatives and missing coverage.

Known nested job names from actual read-only run `34141514828` include
`Architecture Portal / portal`, `Self-test TSan stress / core-tsan` and
`Self-test Release stress / core-stress`; each called stress workflow also has
an unselected skipped sibling. Never confuse those siblings with the canonical
selected job or split names on `/` (`Docs / static` itself contains that string).
The future parent adds `Execute incremental batch / ` to the exact map; O1 must
verify those final names. Only macOS primary has continue-on-error semantics;
an API job failure may correspond to needs success there, not everywhere.

## Verification and gaps

Queued requests may preserve an older `control` than the actual executor SHA.
Before any heavy execution output, preparation verifies both are commit objects
in current main history and compares the exact Git blob bytes of the closed
workflow set: `self-test-report.yml`, `ci.yml`, `core-nightly.yml`, and
`architecture-portal.yml`. Equal source with different SHAs is supported;
changed/missing source fails preflight without heavy work. Runtime independently
checks the same set before consuming evidence. The controller still admits and
claims normally; only after the real executor terminates may missing evidence
clear that slot while preserving verification debt. Source-incompatible request
migration remains a follow-up; this does not claim full fair-queue O1 acceptance.
Real Git regressions changed each of the four files and first demonstrated
incorrect successful preparation, then verified early rejection with no outputs;
a distinct-SHA, identical-workflow case remains executable.

Lowest tier: new actual-workflow-script tests using real temporary Git repos
and real T4d/T4a adapters, plus self-test/topology tests, all CI Python contracts,
the pinned actionlint with its existing exact concurrency.queue exception,
staged ownership and cached whitespace checks. New tests exercise strict entry
resolution, fixed historical control/target, full/focused/none verdicts, preserved
raw needs, unselected unexpected execution, wrong attempts, macOS alternatives
and TSan infrastructure debt. No product timeout or test standard is reduced.
Read-only diff audit also compares each product job block to the T4c baseline;
permanent existing topology/resource tests continue to own their invariants.

These tests execute preparation and verdict scripts, not real product workloads.
Actual reusable call identity, nested API names, secret/permission passage,
runner capacity locks, checkout on each physical host, artifact visibility,
cancellation and completion wakeup remain O1. No remote mutation/fault injection
is performed. Caller journal/claim and result authentication belong to their
separate implementation Tasks; this callable surface does not initialize them.

Official platform facts checked:

- [Reusable workflow context and permission reduction](https://docs.github.com/en/actions/reference/workflows-and-actions/reusing-workflow-configurations#github-context).
- [Workflow ref context](https://docs.github.com/en/actions/reference/workflows-and-actions/contexts#github-context).

Pitfall impact: none. Existing scope/evidence separation, false-green avoidance,
complete journeys and synthetic-platform gap guidance applied; no qualifying
production incident is invented from local tests.

## Documentation Impact

Documentation impact: none

Reason: Inert reusable CI entry only. No Portal current-state/identity or Product
Assembly change; T5 retains the live cutover documentation obligation.

## Version Management

Version impact: none

Reason: CI wiring only; no product/module/contract version or Product Build,
tag, release, publication, deployment or Channel promotion.
