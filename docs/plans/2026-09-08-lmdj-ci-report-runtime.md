# Incremental report runtime composition

## Task and declared files

One local Conventional Commit, not workflow rollout or remote storage creation:

- `scripts/ci/report_runtime.py`
- `tests/build/ci_report_runtime_test.py`
- `docs/plans/2026-09-08-lmdj-ci-report-runtime.md`

Base main includes the actual review consumer, durable outbox and main runtime
with queued aggregate writer compatibility. Existing modules/workflows are not
edited. Root owns separate workflow wiring and reserved outbox Issue setup.

## Authority and operations

Closed config has `scheduler` and `outbox`, each the existing six-field Runtime
config. Repository, workflow ID and bot ID must match; Issue number and node ID
must differ. Do not guess or automatically discover/create the reserved Issue.
All entrypoint operations use existing Runtime authentication: frozen main
checkout, real first-attempt active Incremental batch controller job and the
same short `self-test-report` writer lock. No PR API or additional permissions.

CLI takes `--config PATH --root PATH --summary PATH`, then:

- `init-outbox`: initialize only the explicitly configured empty reserved
  outbox Issue with Runtime.initialize; no scheduler bootstrap or tested cursor.
- `review --run-id ID --attempt N`: real collect validates original exact-run
  review ZIP/history/source/historical policy, then Report goes through Outbox.
  Valid reviews (including findings) and closed-map runs are not backend failure.
- `batches --limit N`: authenticate the complete scheduler journal, replay its
  historical policies, then project every durable result (including before
  advance) to reports. Limit bounds new report observations, not journal reads.
- `drain`: resume one frozen queued payload without rereading source artifacts;
  uncertain claimed POSTs permit only receipt reconciliation, never resending.

Important: Journal.load can PATCH a pending anchor. The scheduler reader wraps
its anchor to reject replace, requiring controller recovery instead. It reuses
Controller._replay with side-effect callbacks prohibited, not reconcile, and
never appends a scheduler event. The independently configured outbox journal
retains its own normal pending-write recovery.

## Report semantics

Recompute scoped result.reference with the historical request.control policy,
identity from the journal request and executor, frozen selection, and original
verdict observations. Compare projected outcomes with the durable result.
Neither requery expired executor artifacts nor convert into legacy release
evidence. Same-suite actual failures and uncovered debt produce separate
suite/class observations, keeping both facts visible in each body. Not-selected
is not passed, none is not overall green, and historical candidates cannot
advance an automatic cursor or clear newer debt.

Only exact `not-required:REQUEST` plus empty selection/outcomes is silent.
Only exact `missing:REQUEST` plus nonempty all-missing selected outcomes creates
missing-evidence reports, explicitly without inventing a product verdict.
Unknown/empty/invalid references and missing historical policy are errors.

Reuse existing self-test suite/class bucket keys and the review backend-failure
key. Batch observations digest epoch plus complete request/executor identity,
suite/class and evidence digest; exact SHAs, scope and evidence remain visible.
Body rendering is deterministic and bounded, with detailed job diagnostics
truncated as presentation only (complete original verdict remains in journal).
No report closes unresolved defects or authorizes release.

All planned bodies are checked before delivery. Previously queued/delivered or
uncertain observations do not consume the new-observation limit, so an old
claim cannot prevent later reports from acquiring durable queued intent across
invocations. Remaining count is explicit; this module adds no background loop
or automatic wakeup. Workflow continuation belongs to the separate wiring.

## Verification and acceptance journeys

Lowest tier: `python3 tests/build/ci_report_runtime_test.py`; then existing
review-consumer/outbox/runtime contracts and all `ci_*test.py` contracts with
pinned actionlint. Stage the three files before `ci_change_scope_test.py`.
No new required gate, threshold or lane-selection change.

Local results: 36 new runtime tests and 1,384 complete CI contract tests passed
with pinned actionlint, with no skipped tests. These are local protocol results,
not evidence of deployed workflow wiring or successful remote O1 acceptance.

- Real executor fixture execution/needs/verdict ZIP -> actual result_for ->
  authenticated journal reference -> delete source artifact -> report Issue ->
  durable outbox receipt. Assert complete verdict digest and scheduler bytes
  unchanged on the far side.
- Real review consumer ZIP/context/history -> independently recomputed all-three
  failure -> actual Report -> authenticated separate outbox -> actual fake HTTP
  Issue body/receipt; repeat delivery without a second Issue.
- CLI config/exact run/attempt -> real consumer -> durable Issue, plus sanitized
  error/nonzero exit. Valid findings and closed mapper produce no write.
- Pre-advance results and a historical candidate remain reportable without
  advancing/rewriting scheduler state. Mixed failure+missing gives both reports.
- Real Git policy change/new controller run -> historical policy replay -> old
  exact evidence still reported; identity/outcome/reference mutations reject.
- Visible pending scheduler append -> forbidden anchor repair -> unchanged
  checkpoint/no report POST. Edited authenticated history and deleted tail fail.
- Queue/claim -> POST then process death -> new driver receipt recovery, or
  invisible receipt -> explicit needs-reconciliation -> exact receipt visible
  -> delivered without another POST. Queued payload drains after artifact loss.
- Small limit -> later observations next invocation; unresolved early claim ->
  later queued intent; frozen-body conflict rejects without business rewrite.

Fixtures use real protocol modules and exact HTTP shapes, not live GitHub.
Hosted permission enforcement, actual concurrency ownership, event delivery and
real API visibility/last-editor behavior remain O1 acceptance gaps. Existing
outbox tests separately cover 404, unknown POST responses and claim-before-send
death. None of those ambiguous outcomes is called successful recovery until an
exact receipt is visible and durable. All writers must route through the same
outbox before claiming cross-process protection; legacy bypass is not protected.

Pitfall impact: applied existing fixture strictness, authorization-as-absence
and full-journey guidance. No new platform incident or qualifying recurrence
was discovered; scheduler load behavior is derivable from repository code.

## Documentation Impact

Documentation impact: none

Reason: Internal report composition; no Portal routes, projected identities or
product source facts change. This plan records unshipped wiring/O1 boundaries.

## Version Management

Version impact: none

Reason: No Product, Module, Provider or Contract identity changes.
