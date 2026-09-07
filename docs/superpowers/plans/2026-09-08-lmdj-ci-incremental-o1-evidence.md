# Incremental CI O1: actual platform evidence

This is an acceptance ledger, not a claim that automatic cutover is complete.
The existing daily product test and missing-batch alert still run. T5 may retire
them only after the remaining real journeys are verified. No release operation
is part of this ledger.

## Declared files

- This ledger only.

## Implemented prerequisites

The reusable execution adapter landed in PR #803 at
`079896aa4de0f92ebf94476e8e69501e9ffebce4`; authenticated runtime in PR #804 at
`2f9ce089ecf664aedd58a22a79142df50b829ff2`; backend-failure consumer in PR #805 at
`d0129dad6fdd1eaa3213a518c1adaaec0d19700b`; manual rehearsal entry in PR #806 at
`24ee0c4f79e0fe21a89be8813cb0566948583aa4`.

## Verified initialization

[Isolated journal #807](https://github.com/endaye/lmdj/issues/807) was explicitly
reserved with the exact empty template and zero comments. Its fixed GraphQL
identity is `I_kwDOTK_1fs8AAAABQJKJ5w`; workflow ID is `352307416`; epoch is
`o1-incremental-20260908-issue807`. Initialization was dispatched once on main.

[Run 34155296101, attempt 1](https://github.com/endaye/lmdj/actions/runs/34155296101/attempts/1)
completed successfully at control `24ee0c4f79e0fe21a89be8813cb0566948583aa4`.
The actual `Incremental batch controller` job succeeded; legacy reporter and
`Execute incremental batch` were skipped. Artifact `10030748821`, named
`batch-controller-34155296101-1`, contains the actual result:
`action=initialized`, `request=null`, `state=null`, executor run/attempt matching
the API identity. It expressly says there is no tested baseline.

A separate GraphQL reread confirmed the fixed Issue remains OPEN, has zero
comments, and has a checkpoint with both head and pending null. Its last editor
is the Actions bot, edited at `2026-09-07T19:22:11Z`; the checkpoint writer binds
the exact control, workflow, controller job, run and first attempt. No product
test, processed baseline or healthy baseline was invented by initialization.

## Bootstrap admitted; final execution still pending

[Run 34155431379, attempt 1](https://github.com/endaye/lmdj/actions/runs/34155431379/attempts/1)
was dispatched with reconcile and no explicit request. Its completed controller
retained artifact `10030801373` (`batch-controller-34155431379-1`). The actual
artifact binds request `batch:o1-incremental-20260908-issue807:1`, kind bootstrap,
null base, target and control `24ee0c4f79e0fe21a89be8813cb0566948583aa4`, policy
`bc6834ca20b75872c42c92c3e5c5ac1fcc3d515889f4544cb37aff27620ea1c6` and all 16
suites, including TSan and Release stress. The output is execute only after
generation 3 with a durable claim for this exact executor. Processed remains
null, results empty and history unknown until actual terminal settlement.

Independent API reads observed the controller already completed while reusable
CI contract, Deploy contract, Chameleon Lab and macOS primary jobs ran, and
other selected host jobs queued. Change Scope and Docs / static had succeeded.
The journal contains three events with an anchored head and no pending write.
This proves real admission and caller execution, not final selected-suite
coverage, terminal verdict validation or successful full testing.

## Remaining real journeys

- During-active repeat reconcile failed in real
  [run 34155641593](https://github.com/endaye/lmdj/actions/runs/34155641593/attempts/1),
  with no controller result artifact. The bootstrap was still nonterminal;
  the API reported its whole-run status as queued while its controller was
  already completed and product jobs remained queued/running. The transport's
  historical writer status restriction was a candidate cause, not a proven
  historical exception: a later exact-attempt read was in progress and its
  journal authenticated. This is a failed O1 leg, not proof of successful
  repeat reconciliation. No batch was
  cancelled, journal reset or second heavy execution authorized by this run.
- Actual nested product job identities, complete scoped verdict and raw needs
  must be checked at whole-run termination, then result and advance reread.
- Real none and focused intervals require genuine main changes and valid
  reviewed-head merge maps. Existing CI-only changes cannot be relabeled none.
- Multiple merges while active must coalesce to the complete first-parent
  interval and fixed latest target, not one heavy run per PR.
- Failure reporting, durable outbox, terminal retry/recovery, no-change idle,
  manual full candidate and final trigger/documentation cutover remain open.
- Runtime has no CLI resume operation yet. A local controller resume fixture
  does not verify recovery of a paused real debt queue.

## Subsequent active observer verified

After PR #809 added narrowly authenticated queued-parent compatibility,
[run 34156325323](https://github.com/endaye/lmdj/actions/runs/34156325323/attempts/1)
completed successfully at main `7abb130b311e9655eac1354e92f50c13d65f3af7`.
Its actual controller artifact returns waiting, retaining the original
bootstrap request, target and active executor/claim `34155431379/1` unchanged.
Generation is 4 with one additional observe event; pending is the newer main
`7abb130b311e9655eac1354e92f50c13d65f3af7`, processed is still null and there is
still only one request with no result. The actual product execution job was
skipped and the controller succeeded. Main advances during the first batch are
therefore being retained without a second heavy launch. This does not prove
the earlier failed observer's exact cause or terminal next-batch coverage.

The first bootstrap's CI contract failure was separately traced to the new
workflow bridge test using a shallow CI checkout as its provenance fixture.
Deploy contract failed on the older #766 canonical-document inconsistency.
These are actual test failures, not evidence expiry or runner unavailability;
the original red run remains red even after their fixes land.

None admission can return idle while its durable claim is still active. The
whole run must terminate and a later settlement must retain not-required before
calling its processed target verified. An explicit node/candidate request is
always full; it is not a way to manufacture focused acceptance.

## Real review limitation

PR #803 review run `34154005940` retained not-reviewed with all three backends
failed; there was no valid AI scope. It was merged before the publisher began.
The closed mapper `34154278366`, artifact `10030414406`, is authenticated but
incomplete with no scope records and explicit full fallback gaps. That is not
none/focused evidence. Early merge with late review remains a conservative
over-testing case; accepting late historical identity needs a separate design,
not removal of current-head authentication.

## Verification

Check linked actual run/Issue identities against the API and download actual
controller artifacts; do not substitute local mocks for the claims above.
For this explanatory ledger, run docs-static and staged ownership checks.
Portal check was also attempted as required: 54 tests passed and three failed
because this isolated worktree lacks glob, gray-matter and cheerio. No Portal
pass or build is claimed; no Portal source is changed by this ledger.

## Documentation Impact

Documentation impact: none

Reason: an explanatory acceptance ledger only; no Portal routes or current
automatic testing behavior change. T5 owns current operational documentation.

## Version Management

Version impact: none

Reason: no Product Build or other product identities, tag, Release, publication,
deployment or Channel promotion. Recorded Git/run identities are audit facts,
not allocated product revisions or a release snapshot.

Pitfall impact: none — existing whole-journey and actual-platform evidence
guidance applied; unfinished transitions remain explicit.
