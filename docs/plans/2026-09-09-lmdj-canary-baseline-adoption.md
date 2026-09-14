# Adopt the approved first version baseline in durable planning

Status: source implemented and locally verified within the limits below;
no live storage initialization or activation.

## Scope and decision

Implement the owner decision retained in PR #1071 through the existing Canary
Planning entry, not a new unused library. Add the manual-only operation
`adopt-version-baseline` with an empty request. The authenticated frozen control
reads the reviewed baseline configuration and the two actual Host manifests at
the exact approved first-parent main revision. Caller-supplied SHA, progress,
manifest or receipt is not accepted.

The approved revision is `a81faad3b85d362e3e44541cd28ee21dac6848a4`; both Host
manifests there declare `4.1.0`. Do not bump versions or backfill changelogs.
Configuration source is `tools/canary/first_version_baseline.json`, bound to the
owner's recorded decision. Current Host versions may differ without changing
the historical baseline; verify its manifests at that revision, not current HEAD.

Declared files:

- `tools/canary/first_version_baseline.json`
- `tools/canary/planning_entry.py`
- `tools/canary/planning_journal.py`
- `.github/workflows/canary-planning.yml`
- `tests/build/ci_canary_planning_entry_test.py`
- `tests/build/ci_canary_planning_journal_test.py`
- this plan and `docs/plans/2026-09-09-lmdj-result-driven-delivery.md`
- `apps/docs-site/docs/operations/testing-and-proof.mdx`

## Durable transition and boundaries

Explicit journal initialization and all-null progress bootstrap remain separate
prerequisites. Adoption requires a pristine bootstrapped planning state with no
observations, active/pending plan or unfinished write. A small sealed adoption
receipt retains complete approval bytes and both manifest bytes with their Git
blob identities. Store it in the same authenticated planning Journal using the
existing event/checkpoint and unknown-write recovery protocol.

Only `version_accounted` becomes the approved revision plus adoption receipt
digest. All site and formal pointers stay null. No scheduler state, failures,
verification debt or existing changelog changes. Same complete adoption returns
the original receipt/progress without appending another event, including after
later observations. A changed receipt, unapproved import or attempted migration
of existing plans fails closed. Receipt identity excludes transient observer
run/main/control values so unchanged approved bytes survive a moving control.

The subsequent real result planner must read this persisted version progress,
not the scheduler request's base. Site bootstrap still contributes its full test
floor; this Task does not claim a narrower first site deployment. Targets older
than the version baseline remain rejected, not silently discarded. Automatic
discovery's older historical wakeups require a separate reviewed reconciliation
policy before activation; do not reset scheduler history or forge site progress
to get around that boundary. Automatic readiness remains off.

## Verification and complete acceptance journey

1. Red-first regressions for absent adoption behavior and invalid requests.
2. Actual CLI/authenticated Runtime with GitHub-shaped HTTP transport fixtures:
   explicit bootstrap, adoption event/complete receipt, new OS process replay,
   duplicate adoption without new append. Remote state is serialized across the
   process boundary; no in-memory journal instance substitutes for recovery.
3. Persist an actual subsequent test result in the scheduler fixture, observe it
   through the existing entry, then verify actual `plan_after_result()` output.
   Deliberately separate approved version baseline and scheduler request base;
   assert every first-parent commit between baseline and target is present.
4. Compare complete scheduler state/failure/debt bytes before and after; assert
   site/formal remain null and site bootstrap full-scope selection is preserved.
5. Reject caller evidence, malformed/changed approval, wrong manifest/version,
   side-branch revision, missing bootstrap, prior observations, automatic caller,
   wrong lock/run/attempt and tampered receipt without business writes.
6. Inject response loss around event/checkpoint writes and replay in a new
   process; preserve original bytes and recover positive receipts without blindly
   repeating an uncertain POST. Retain historical target refusal explicitly.
7. Focused planning suites, complete `ci_*_test.py` discovery with available pinned
   actionlint/ShellCheck, staged new-file ownership, Portal check, version verifier,
   final committed range classification and exact-head independent review.

Fixtures do not establish real Actions token/environment behavior, reserved live
storage, backend execution, VM isolation, delivery or publication. No live journal
is initialized or adopted by shipping this source change. No new required PR
gate, weakened test, changed timeout or reduced coverage is part of this Task.

## Local verification evidence

- Planning-focused discovery: 107 tests pass, independently repeated; entry 46
  and journal 27 include the new actual CLI/process and unknown-write journeys.
- Complete `ci_*_test.py` discovery: 2,213 tests executed, one inherited failure
  in `ci_pitfall_ledger_test`. The unchanged
  `snapshot-page-pin-only-fires-at-freeze.md` uses unknown `area: docs`.
  [Issue #1078](https://github.com/endaye/lmdj/issues/1078) retains the defect;
  the ledger entry and validator match the task's main baseline exactly. This is
  not a green full CI result, and the Task does not suppress or repair that test.
- Portal: 113 tests, production build, 44 routes and internal links pass.
- New-file ownership after staging: 66 tests pass. Product version verification
  passes without changing active versions or allocating a Build.
- Pinned actionlint 1.7.12 with explicit ShellCheck 0.9.0 passes the changed
  workflow; only the existing exact `concurrency.queue` compatibility exception
  is used. All concurrency and permissions assertions remain enforced.
- Ordinary CI-contract checkout is shallow. Tests use complete temporary Git
  histories for runtime authentication, rather than requiring historical objects
  in the source checkout. Repeat the planning suite from an actual depth-one
  clone of the final commit before push; retain that result in the PR.

No new pitfall record: the retained ledger failure is an existing guarded defect,
and the runtime invariants have direct regressions. This Task does not grant
infrastructure, live storage, deployment or release authority.

## Version Management

Version impact: none

Reason: internal version-history progress adoption only; active Product, Host,
Module, Provider, Contract, Assembly, changelog, tag and snapshot inputs unchanged.

## Documentation Impact

Documentation impact: required

Affected portal pages: /operations/testing-and-proof/

Reason: document the new manual operation, prerequisites, receipt recovery and
historical-wakeup activation gap without presenting adoption as delivery evidence.
