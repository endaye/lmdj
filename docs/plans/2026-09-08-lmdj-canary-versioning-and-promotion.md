# Implement conditional canaries and exact-candidate promotion

September 9 update: the [result-driven delivery plan](2026-09-09-lmdj-result-driven-delivery.md)
supersedes daily deployment and the ordering below. Verify incremental testing
and Issue reporting first; then continue the candidate tasks with result/manual/
recovery wakeups, independent canary sites and a verified Netcup deployment
boundary. Autonomous Issue repair/merge is excluded. Existing T1 tooling is
reused, not restarted; the older T2–T8 details remain inputs subject to this update.

Date: 2026-09-08

Status: staged implementation plan; T0 is documentation only. No rollout,
signing configuration, Product Build or release operation is authorized by this
file. Proposed defaults and activation decisions are distinguished in the
[spec](../design/2026-09-08-lmdj-canary-versioning-and-promotion.md).

## Outcome and constraints

Deliver daily/manual change-based canary preparation, per-Host changelogs and
docs aggregation, and owner-selected exact-canary formal promotion. Preserve
ordinary lightweight PR merges and main-only incremental testing. Do not add
daily full tests or restore strict main-update requirements.

One Task is one reviewable Conventional Commit in an isolated worktree. Each
Task below declares its ownership boundary, lowest-tier verification and
far-side acceptance. Large Tasks split into named sub-Tasks before editing;
their concrete file lists must be recorded in a focused execution plan. Proposed
new paths are not claims that files or commands already exist. New files acquire
explicit scope ownership and executable test registration in their introducing
Task. No new global required PR check is planned.

## T0 — Design and plan (this Task)

Declared files:

- `docs/design/2026-09-08-lmdj-canary-versioning-and-promotion.md`
- `docs/plans/2026-09-08-lmdj-canary-versioning-and-promotion.md`
- `.agents/pitfalls/worktree-checkout-flattens-symlinks.md`

Deliver a coherent proposed contract and explicit activation blockers. Do not
edit current governance to announce unimplemented behavior or mark the stable
question resolved. No pitfall recurrence is claimed from hypothetical failure
cases; apply existing recorded guidance to the design. Record the actually
observed worktree symlink-checkout failure from this Task's Portal verification
in the declared pitfall entry; restoring pristine links changes no source bytes.

Verification:

- Check both documents' relative links, scope/authority language, Task coverage
  of all spec acceptance rows, and complete Version/Documentation sections.
- `python3 tests/build/ci_change_scope_test.py` after staging new files.
- `git diff --cached --check` and exact declared-file inspection.
- Run the repository pitfall-ledger contract test for the added environment
  finding; its occurrence links the actual reproduction baseline, not a guessed
  introducing commit or an invented remote run.
- `scripts/architecture-portal.sh check` as the supplied Task instruction
  requests; distinguish an environment/pre-existing failure from a docs defect.
- After commit, `scripts/local-ci.sh --base-ref origin/main --list --json`.
- Validate the PR body with `tests/build/ci_pr_body_lint.py` and declaration-only
  local CI. Obtain current-head review or record an actual agent takeover.

Far-side result: reviewed docs commit/PR, no running automation changed. All
implementation and live acceptance rows below remain unexercised by T0.

T0 local verification: both document link/declaration checks passed; staged
ownership passed 66 tests; pitfall ledger passed 14 tests. The complete Portal
check passed 86 tests, 39 current pages, 10 diagram sources/20 outputs, the
current snapshot check, typecheck, build and 42-route/internal-link validation.
Its first attempt failed on a flattened checkout symlink; the declared ledger
entry records the environment-only recovery and unchanged test assertions.

## T1 — Read-only batch planner and durable record contracts

Depends on T0. Begin with a focused execution plan and regression fixtures.

Proposed declared files: `tools/canary/planning.py`,
`tools/canary/records.py`, `tools/canary/policy.json`,
`tests/build/canary_planning_test.py`, `tests/build/canary_records_test.py`,
plus the exact existing scope/test registration files identified by that plan.

Implement pure planning over complete commit intervals and dependency closure,
site-specific deployed baselines, a distinct version-accounted baseline and
formal baseline, pinned input/record digests and typed failure states. Reuse
existing collectors and scope closure rather than reimplementing Git history.
Define operation idempotency, receipt schemas, storage interface and fencing
contracts without writing GitHub or allocating a version. A CLI preview, if
included, is read-only and names no live candidate by guesswork.

Lowest-tier tests: real temporary Git histories (including renames, deletions,
reverts and moving targets), pure planner fixtures, corrupt/missing storage and
fencing model tests. Expected results distinguish no-change from unavailable.
The complete-candidate build set and selective-deployment set are separate
outputs. Test duplicate manual/daily IDs and cumulative missed-schedule scope.

Version impact: none; internal orchestration only.
Documentation impact: required when a user-facing preview entry point ships;
otherwise none with a concrete reason in the execution Task. Do not document
planned automation as active.

## T2 — AI assessment and canonical version/changelog preparation

Depends on T1. Split into T2a (read-only assessment), T2b (local preparation)
and T2c (PR/cut reconciliation), each a separate reviewed Task.

Proposed ownership: `tools/canary/assessment.py`, `tools/canary/preparation.py`,
`tools/canary/cut.py`, matching `tests/build/canary_*_test.py`; reuse the existing
`scripts/ci/review_pipeline.py` adapter contract and canonical version, lock,
identity and snapshot generators. Any changes to those shared files are declared
in the corresponding focused plan, not incidental edits.

T2a binds complete input coverage to GLM/Kimi/Grok result records. Enforce
structured advice, safe references, no command/write authority and bounded
fallback/Issue outbox behavior. T2b computes exact component bumps without
double-counting pre-bumps and generates per-Host changelogs in a temporary test
repository. No real version is allocated by these tooling Tasks. T2c implements
short-lived version PR planning, atomic expected-head checks, post-squash
coverage reconciliation, occupancy audit, three-attempt limit, post-merge
witness integration and durable no-reuse accounting. Remote writer integration
stays disabled until activation.

Tests: invalid/truncated/model-injected advice, valid fallback chains and all
backends failed; patch/minor unions and ambiguous major; shared dependency
effects and version pre-bumps; stale real generated identity; known-occupied
positive control; main advancing at every cut boundary; crashed writer fencing;
review invalidation after changed head; retained occupied/superseded cuts.

Defects prevented: invented or duplicated versions, misleading changelogs,
unreviewed merged inputs and reused allocations. Each error states why/remedy.

Version impact: none for tooling. Actual allocation later declares exact
versions from manifests and requires snapshot/current portal updates.
Documentation impact: required for implemented operator preparation behavior.

## T3 — Allocation-only scope proof and cost boundary

Depends on T1/T2's identity contracts; no automatic canaries before completion.

Ownership: a narrowly scoped recognizer under `scripts/ci/`, its actual main
batch planner integration, `scripts/ci/scope_policy.json` only if necessary,
`tests/build/ci_scope_policy_differential_test.py`, matching recognizer and
consumer parity tests. Declare exact files in the execution plan first.

Prove a generated allocation on real trees cannot erase substantive changes
from the cumulative business interval or outstanding verification debt. Compare
old/new generators, payload inputs, manifest/lock semantics and downstream
consumers; unknowns retain full. Do not trust bot authors, labels or filenames.
Keep required version/generated-facts/snapshot validation. Do not lower a
coverage floor, omit actual dependency tests or turn complete formal evidence
into focused evidence.

Lowest-tier tests: real-tree differential cases for identity-only cuts,
substantive Assembly edits, changed schemas/providers/toolchains, generator drift,
forged bot commits and intervals combining a cut with foundational changes.
Run the complete scope and incremental selection consumer suites. Measure the
remaining scheduled build/test cost before making a capacity claim.

Version impact: none. Documentation impact: required for changed test-selection
semantics on `/operations/testing-and-proof/`. If safe narrowing is not proven,
retain current behavior and keep automatic cut activation blocked.

## T4 — Per-Host changelog presentation

Depends on T2b's changelog format, independently developable from T3/T5.

Ownership: canonical `CHANGELOG.md` under each affected active Host directory;
`apps/docs-site/scripts/` parser/generator and tests; generated changelog routes
under `apps/docs-site/docs/`; existing navigation and fact/identity checks.
Record exact Host and route inventory before editing. Do not invent historical
versions or retrospectively claim deployments.

Tests: multiple Hosts at different versions; unchanged Host; shared Core effect;
reverted feature omitted; escaped content; invalid/duplicate version references;
prepared vs deployed vs promoted status; older stable manual; promotion addendum
without changing frozen Host entries or snapshot bytes. Run docs-site check.

Version impact: none for presentation tooling; assess any shipped Host UI changes
separately. Documentation impact: required; name all new changelog routes and
`/operations/version-and-release/` in the execution Task.

## T5 — Complete canary preparation and isolated signer integration

Depends on T2c and closed canary admission policy. Split policy/verifier, isolated
signer adapter and disabled workflow wiring into separate Tasks.

Ownership: existing `tools/release/` policy/model/audit/preparation modules and
profile verifiers; a narrow new `tools/canary/` signing request adapter; matching
release/canary tests; later a disabled dedicated canary workflow. Reuse
`scripts/release.sh` as the release boundary, extending it under reviewed policy;
do not introduce handwritten tag/Release commands or a parallel release stack.

First publish an explicit canary test inventory derived from real package
builders and selected main suites. Retain exact identity, package verifiers,
signatures, complete assets and current-policy formal promotion requirements.
Audit must distinguish historical published canary validity from fresh formal
eligibility; no published exception bypasses the latter.

Signer activation requires owner-approved actual executor/key-custody and
request authentication. Use isolated ephemeral test keys and strict fake APIs
for local tests. Live Product keys are not needed to implement this Task.

Tests: both Host packages bound to one revision; missing/wrong/extra inventory;
local unsafe signer caller; forged request and replay; private-key isolation;
offline/restarted signer; allocated build failure; Draft partial upload and
unknown API outcome; immutable complete publication; no full test from calendar
alone. No promotion by rebuilding bytes. Verify cache keys include exact inputs.

Version impact: none unless public package format or Assembly changes; then
split and declare that version impact rather than hiding it in tooling.
Documentation impact: required for canary admission and signing boundary.

## T6 — Conditional daily/manual deployment and durable recovery

Depends on T1/T2c/T3/T4/T5. Keep new triggers disabled during development.

Ownership: dedicated daily/manual controller workflow, existing Cloudflare
portal workflow trigger, existing shared Host adapter/transaction and durable
run store integration, matching controller/workflow/adapter tests. Exact paths
are resolved in the execution plan. Do not rewrite the Cloudflare SDK or create
a second uploader. No new infrastructure purchase or secret relocation.

Implement site/channel allowlists, one active coalesced batch, durable receipts,
independent site progress, exact-prior recovery, missed-schedule handling,
manual force boundaries and report outboxes. Scheduling uses the reviewed UTC
cron; displayed dates use explicit timezone. Routine Linux stays self-hosted;
retain the existing macOS hosted fallback only for its authorized workloads.

Tests: no-change/docs-only/one-Host/shared-Core plans, status-update loop
prevention, duplicate daily/manual wakeups, fixed candidate despite later main,
cancel/restart reconciliation, one Host fails, late upload receipt, preview/fixed
route mismatch, bounded readiness, headers/charset/robots, browser side effects,
persisted data recovery, unsafe rollback refused. Verify no calendar-based full
test, per-PR deployment or Release-event fan-out is introduced.

Version impact: none for control plane. Documentation impact: required for site
mapping and actual deployment behavior. Live site configuration is an explicit
activation prerequisite, never inferred from a URL's existing role.

## T7 — Exact-candidate formal promotion

Depends on T5 and a reviewed resolution of the stable-channel question. Reuse
T1's durable records; can develop local policy/API tests alongside T6.

Ownership: `tools/release/promotion.py`, policy/model/audit/API/transition modules,
matching promotion/audit/API/workflow tests and protected publication workflow;
the stable question and decision record, canonical version/release governance
and affected portal pages. Split settled policy/model, remote reconciliation
and protected workflow into independent Tasks before editing.

Define explicit intent for candidate, target channel, Latest and deployment
scope. Default deployment scope is none. Permit only reviewed channel changes,
not tag/asset/source mutation. Keep original Release body/marker and initial
publication facts; append verified promotion receipts and formal summary to the
docs projection. Latest is a separately reconciled global pointer. No extra
Product Build or Host bump on promotion.

Tests: direct canary-to-target eligibility; stable ceiling not raised by merely
adding a command; exact-candidate full evidence with artifact acceptance;
expired evidence reacquired through existing scheduler; failed evidence leaves
canary intact; old published exception cannot grant fresh promotion; main moves
without changing selected candidate; API timeout after successful mutation;
ledger write failure; repeated/concurrent requests; old Latest intent; out-of-band
metadata drift; unchanged tag/asset digests and Host versions after promotion.

Version impact: none for control plane. Documentation impact: required for
implemented channel semantics. A completed local test does not declare the
product stable-ready or perform a real promotion.

## T8 — Controlled rehearsal and trigger cutover

Depends on T3–T7 and the spec's seven activation prerequisites. Record actual
verification as an acceptance ledger, with one far-side assertion for every row
of the spec. Declare exact rehearsal namespace, disposable targets, credentials,
allowed mutations, stop conditions and cleanup before live work. Product tags
and production sites are never disposable fixtures.

First run read-only plans over real main intervals and measured runner/storage
budgets. Then use separately authorized sandbox signing/publication/site
fixtures to exercise each failure and recovery leg. Strict fake API passes are
not live evidence. An unavailable platform or untested leg remains a named gap.

Cut over in small boundaries: docs conditional deployment, canary planning and
preparation, canary publication/deployment, then owner-dispatched promotion.
Disable old overlapping triggers in the same reviewed cutover as enabling their
replacement. Verify exactly one durable owner for every trigger and pending
operation. Do not broadly cancel unknown in-flight work or restore daily full CI.
Retain a pause/reconcile rollback that stops new admission without erasing
versions, receipts, reports or published history. Trigger rollback restores the
recorded prior configuration only when it cannot duplicate active operations.

Deliver an evidence-only record with exact runs/targets, success/failure facts,
queue/build/signing/storage observations and unresolved limits. No claim of
zero total cost: report self-hosted routine Linux and the paid macOS exception
separately. A docs merge is not a live acceptance result.

Version impact: none for rehearsal/control changes; any real candidate allocation
is its own version Task and follows snapshot policy.
Documentation impact: required when activation changes current operation pages.

## Dependency and execution order

Start with T1, then T2a/T2b and T2c. T3 and T4 can proceed independently once
their input contracts are fixed; T5's policy/signing work has no dependency on
the docs presentation. T6 and T7 integrate those foundations, and T8 is last.
This is a dependency map, not authority to start multiple editing agents or to
execute external operations. Shared policy/generator files have one writer per
Task; implementations ship behind disabled activation controls.

## Version Management

Version impact: none

Reason: T0 only adds this plan, its design and an environment pitfall entry.
No current manifest, generated identity, Product Build, Assembly, snapshot,
tag or artifact changes. Future
Tasks must restate version impact from their actual diff and use canonical
allocation, lock, generated identity and provenance tools when applicable.

## Documentation Impact

Documentation impact: none

Reason: T0 changes only a proposed design, plan and environment pitfall entry,
not current Portal pages or documented implemented behavior. Later Tasks explicitly own current portal
updates when their features become implemented; Product Build/Assembly Tasks
cannot use this declaration to waive required pages or immutable snapshots.

## Completion reporting

Report designed, implemented, locally verified, merged, sandbox-rehearsed and
activated separately. Track canary-published, deployed-per-site and
formally-promoted as distinct external facts. T0 completes none of T1–T8 and
does not resolve owner-dependent signing/site/stable activation prerequisites.
