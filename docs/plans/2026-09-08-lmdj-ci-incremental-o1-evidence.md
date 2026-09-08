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
- Real none and focused intervals require genuine main changes and complete
  deterministic Git/policy scope. Valid reviewed-head advice must be retained;
  missing advice uses the spec's deterministic fallback, not fabricated review
  success. Existing CI-only changes cannot be relabeled none.
- Multiple merges while active must coalesce to the complete first-parent
  interval and fixed latest target, not one heavy run per PR.
- Failure reporting, durable outbox, terminal retry/recovery, no-change idle,
  manual full candidate and final trigger/documentation cutover remain open.
- Runtime lacked a CLI resume operation at the first observer. PR #815 has
  since added it; its local tests do not verify recovery of a paused real debt
  queue, and the manual workflow still needs this operation connected.

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
incomplete with no scope records and historical full fallback diagnostics. That
is not none/focused evidence. The accepted spec instead requires a verified
deterministic floor when advice is missing. Preserving valid late historical
advice needs a separate design, not removal of current-head authentication.

PR #812's review run `34156734074`, bound to historical head
`b589400ee4c251cecefd65f54d9b46a11e08f99a`, also retained `not-reviewed`:
GLM and Grok reported runtime failure, Kimi invalid output. Its retained scope
artifact is deterministic `none` for this explanatory ledger, not an AI
approval. Authorized independent current-head review is recorded on the PR.
The real all-backend-failure report through the durable outbox remains an
acceptance gap; the presence of the failure artifact is not a created Issue.

## Subsequent terminal and recovery evidence (2026-09-08)

This update supersedes the earlier pending observations above, without rewriting
their historical meaning. It declares only this ledger, uses the isolated
`docs/ci-o1-recovery-evidence` branch, and changes no workflow or product code.
Daily triggers remain active until the separate T5 cutover. A successful local
check or a completed diagnostic is not acceptance of the whole migration.

### Full execution, debt and reporting

Bootstrap run `34155431379/1` completed with 13 passing suites and three actual
failures: CI contract, Deploy contract and TSan stress. Its terminal result was
persisted by `34158982215/1`; reporting run `34159207772/1` created Issue #820.
Later fixes do not rewrite this historical result.

The next full run `34159345765/1` targeted
`f5ce0b6b0a516001a1611b16a4f45001eab69061`, starting from the bootstrap target.
Its complete first-parent interval contained 11 commits and 31 paths. Fifteen
suites passed; TSan failed before compilation/tests because the runner could
not read `vm.mmap_rnd_bits`. Original verdict artifact `10033180165` has evidence
digest `2da78956699bd6661413bb968d5bb6b5b17d472ed839685e88a09302056e2f85`.
Settlement `34163454728/1` retained the infrastructure debt and prior failures.
Report `34163537574/1` created the separate infrastructure Issue #827.

While this full run was active, observers `34159537840/1` and `34162283852/1`
retained its exact request and claim while recording newer pending main SHAs;
neither started a second heavy batch. The following run `34163559657/1` selected
only executable TSan debt despite its docs-only delta. It hit the same runner
prerequisite failure. Settlement `34163785824/1` retained that debt at attempt 2,
paused it under the existing bound, and preserved all three historical failures.
Report `34163882659/1` appended to Issue #827 instead of creating a new bucket.
These are real full-inventory execution and recovery observations, not a claim
that full testing passed or that the runner prerequisite has been repaired.

### True docs-none, idle replay and focused Host completion

The genuine documentation change in PR #828 produced the exact one-commit,
one-document interval ending at `b70987d01ac5992dcd9ec8c48ea5281f3c00a09f`.
Run `34164008872/1` admitted `none` with no selected suites. Only its controller
ran; no product execution was launched. Settlement `34164114877/1` persisted
`not-required`, then advanced processed progress. Fresh execution-enabled
reconcile `34164206056/1` returned idle with no request and an identical complete
state: no generation change, duplicate admission or heavy run. Paused TSan debt
and all historical failures remained unchanged.

PR #829 changed two Host READMEs and their explanatory plan. Run
`34164424476/1` fixed base `b70987d01ac5992dcd9ec8c48ea5281f3c00a09f` and
target/control `0fedd7268e5f0f9a27390c3d8085387083f46e86`. The actual selection
was exactly `creator`, `docs_static`, `portal`, `web_runtime_host`, and
`web_runtime_lab`. All five passed. The other eleven suites were not selected,
not passed. Original artifact `10034155914` has ZIP SHA-256
`190fd054c9c682cf5b1e356f8388aab1a371d70ae203710e6f6547893543a5a6`
and verdict evidence digest
`b45bc67cc3a41f329cec4b92f61fc39b20e1157dbf05a04fd16d3f8a15940647`.
Independent validation reconstructed the verdict from the frozen request,
historical policy and raw needs, and authenticated all 27 actual job records.
This Host closure includes Creator; it is not proof of two disjoint closures.

During that Host run, observer `34164738962/1` recorded subsequent code merges
as pending while preserving the entire original request, claim, debt and failure
state. Settlement `34166337225/1`, artifact `10034278582`, recorded the five
actual outcomes, cleared active and advanced processed only to the frozen Host
target. At generation 30, pending was the newer
`16e822775d6357861ba37e5a93314ab8995e5d61`. Complete debt and historical failure
objects still matched admission. Focused green did not become full health.

### Actual response-loss recovery and fresh replay

The ordinary, non-diagnostic all-backend-failure report was also completed:
run `34158764724/1` created Issue #819 and replay `34158836074/1` did not duplicate
it. Thus the earlier normal-report acceptance gap is resolved; this does not
turn the original failed review into valid AI advice.

The reviewed isolated storage roles are scheduler #824 and outbox #825; neither
is the main scheduler #807. Run `34165108385/1` stopped with controlled exit 86
after the scheduler's actual append but before acknowledging its response.
Comment `5576019621` existed exactly once with digest
`81ff2ea463fb0a72cc220dbe5a4265fcedb33c6a6fe4afaa3121f06f1c0ba9ac`.
Ordinary settlement `34165196646/1` recovered that existing append; fresh replay
`34165520261/1` kept the complete recovered state and remote journal unchanged.
No product request, result, baseline or heavy execution was created.

Run `34165285937/1` stopped with controlled exit 86 after the actual creation of
diagnostic Issue #836, before delivery acknowledgement. Its source was the real
all-backend-failure observation for PR #812, head
`b589400ee4c251cecefd65f54d9b46a11e08f99a`, review `34156734074/1`.
The diagnostic namespace isolates this exercise from production Issue #819.
Ordinary drain `34165454334/1` found the existing Issue and persisted delivery
comment `5576058486`, with receipt `{issue_number: 836, comment_id: null}`.
It did not invent an acknowledgement or create a second business Issue.
Fresh drain `34165503120/1` left complete journal and business Issue snapshots
unchanged; an all-state Issue inventory still found exactly one matching Issue.
The API did not expose a final step summary; idempotence is established by the
actual far-side state, not by claiming to have inspected that summary.

### Claim-before-output boundary and remaining acceptance

Run `34166438455/1`, at exact control
`16e822775d6357861ba37e5a93314ab8995e5d61`, used the fresh assigned claim journal
#826. The actual controller exited 87 after authenticated durable
observe/admit/claim events and before any execution output. Its full bootstrap
request selected all 16 suites, with null base and the current run as executor.
All three journal envelopes were independently authenticated and hash-replayed;
the anchored head was
`5f33af4b113529bd175048903fc8a3ae5594b1434a293784f93bf48865dd90b4`, pending null.
The terminal run had only the failed controller and two skipped jobs, and zero
artifacts. No product test ran. This proves the controlled exit boundary, not
GitHub cancellation.

Fresh ordinary settlement `34166543480/1`, artifact `10034333280`, then persisted
the result before advance. Complete authenticated history was exactly
observe/admit/claim/result/advance, retaining the original three records without
any changes. Generation 5 cleared active and advanced processed to the fixed
target, but recorded every one of the 16 selected suites as missing, with debt
at attempt 1 and no invented test failures. This is processed, not tested.
Fresh settlement replay `34166702231/1`, artifact `10034378791`, returned idle
with no request and a complete state identical to the first settlement,
including generation 5, all original request/result identities and every debt's
attempt count. No execution-enabled recovery was used in either settlement.

At that recording point, outstanding legs included real GitHub cancellation
and preserved missing-suite debt, and later docs-only changes retaining that
debt. The subsequent evidence below narrows these gaps, without claiming an
interrupted-process cancellation pass. Still outstanding: exact full candidate acceptance
from the new source; remaining completion-boundary/consumer-union journeys;
automatic main/completion/independent-health-tick cutover and real chain-limit
recovery with idle verification. An actual valid Kimi fallback after GLM failure
has not been observed; existing real evidence proves all-backend failure, while
the bounded successful-fallback matrix is local-test evidence. No tag, Release,
version allocation, deployment or Channel promotion has been performed.

### Subsequent C1 documentation observer

This one-file update uses isolated branch `docs/ci-o1-cancellation-evidence`,
based on `e5412a4b1359dd928b556379c4195ffc05ed014d`. It records observations;
it does not change code, storage, triggers or the acceptance standard.

The genuine one-document merge #839 ended at
`aca410cbc2bdeb8a31c01e0a4ceb1df9d6269979`. Its complete interval from the
previous C1 target selected deterministic `none` under both policy versions.
[Observer 34166959881/1](https://github.com/endaye/lmdj/actions/runs/34166959881/attempts/1),
artifact `10034462772`, ran settlement-only, not execution-enabled reconcile.
The actual original controller result changed only events, generation and pending
in the complete scheduler state: generation became 6 and pending became that
documentation SHA. All 16 missing-debt objects, requests, results, failures and
processed progress were exactly unchanged. Only the controller succeeded;
legacy reporter and product execution were skipped.

This proves observing a genuine later documentation change did not erase C1
debt. It is not an execution-enabled debt-processing pass and does not claim
the pending documentation interval was completed.

### C2 actual cancellation terminal, timeout race and recovery

The separately reviewed fixed claim role moved to fresh
[journal #840](https://github.com/endaye/lmdj/issues/840), node
`I_kwDOTK_1fs8AAAABQKYSiQ`, epoch `o1-claim-cancel-20260908-issue840`.
Previous claim journal #826 was preserved. Initialization `34167612410/1`,
artifact `10034662007`, established an empty checkpoint at control
`e7fc6959134a434a95a5cbfc8e755ff9b18efede`; this was not a tested baseline.

[Diagnostic 34168119615/1](https://github.com/endaye/lmdj/actions/runs/34168119615/attempts/1)
fixed target/control `e5412a4b1359dd928b556379c4195ffc05ed014d` and request
`batch:o1-claim-cancel-20260908-issue840:1`. Its actual bootstrap selected all
16 suites with null base. Complete pre-cancel GraphQL records
`5576390280`, `5576391486`, `5576392030` were observe/admit/claim, authored by
stable Bot node `MDM6Qm90NDE4OTgyODI=` without comment edits. Every envelope's
previous link and digest was recomputed; the checkpoint head was
`8e8c1093ad86b9aec863af88d87e001e2cf8d1e262823087e6aa367cb0acefad`, pending null.
Actual historical Git policy and reducer replay bound the claim to this run's
first attempt, with no processed baseline or invented test outcomes.

The controller job `101883109982` succeeded; the independent, unprivileged
waiter `101883240654` was observed in progress after the short writer lock had
ended. Legacy and product execution jobs were skipped, and artifact inventory
was zero. One ordinary cancellation POST was accepted at `22:57:53Z`; it was
not repeated. The API subsequently reported both parent run and waiter job
`completed/cancelled`, with parent updated at `22:57:55Z`.

**Timing limitation:** the original waiter log first records natural expiry at
`22:57:53.2122906Z`, after its 285-second sleep, then exit 1 at
`22:57:53.2139369Z`. Its actual wait step concluded failure, before the job/run
reached cancelled. Therefore this is not evidence that cancellation interrupted
a still-running wait process. The real cancelled executor's recovery below is
verified; the interrupted-process leg remains open. A successful cancellation
API response or cancelled job label alone cannot erase this race.

The complete GraphQL response after cancellation matched the pre-cancel ready
snapshot exactly: body, editor metadata, all three comments and pagination.
No product jobs or artifacts appeared. Ordinary settlement
[34168456440/1](https://github.com/endaye/lmdj/actions/runs/34168456440/attempts/1)
then succeeded, with original artifact `10034927085`, ZIP SHA-256
`66d3e4841ad51a5a92f0ce84b4d4a6e03a80165e5a139250720091541dcef532`.
It preserved all three original comment objects unchanged and appended result
`5576437322` before advance `5576437815`. Replaying all five authenticated
events with the real historical policy reproduced the entire original result
state: generation 5, active null, all 16 suites missing with debt attempt 1,
no invented test failures. Processed advanced to the frozen target, not to a
tested or healthy baseline.

Fresh ordinary replay
[34168494357/1](https://github.com/endaye/lmdj/actions/runs/34168494357/attempts/1)
retained artifact `10034936370`, ZIP SHA-256
`d1b9f6620f3d4cb376c6a320ecb7cadcd6f5bd993bceb252746da4c7650ce9cc`.
Both original ZIP hashes matched their API digests. Replay returned idle with
no request and a complete state identical to settlement. The entire GraphQL
response also remained identical, including all five comments and metadata.
Both recovery runs had four jobs: controller success, legacy reporter, waiter
and product execution skipped. No repeated admission, debt-attempt reset or
product execution was hidden by the replay.

Original API responses, complete snapshots, waiter log and both original ZIPs
were retained outside the worktree at
`/tmp/lmdj-o1-C2-independent.usuSfl`; that local path is an investigation copy,
not a permanent remote storage guarantee. The remaining candidate, execution-
enabled debt, completion/consumer-union, real interrupted-process cancellation
and T5 cutover/chain-limit journeys remain open. Nothing here authorizes a
release or states that automatic cutover is complete.

### C3 running-process cancellation, ordinary settlement and replay

This subsequent one-file Task uses `docs/ci-o1-live-cancel-evidence`, based on
`fe043fd3a2a06dfbca4088cc59e0e8ef6997f336`. Its only declared file is this
ledger. It does not rewrite the C2 expiry race above: that earlier attempt did
not prove a running-process interruption. C3 supplies a separate real journey
with fresh storage, not a reset or reinterpretation of #840.

The reviewed binding in PR #864 reserved
[journal #857](https://github.com/endaye/lmdj/issues/857), node
`I_kwDOTK_1fs8AAAABQLLT3w`, epoch
`o1-claim-cancel-live-20260908-issue857`. All four following runs used exact
control `fe043fd3a2a06dfbca4088cc59e0e8ef6997f336`, existing workflow
`352307416`, and attempt 1. The root performed the separately authorized
dispatches and one normal cancellation; independent verification was read-only.

[Initialization 34174908092/1](https://github.com/endaye/lmdj/actions/runs/34174908092/attempts/1)
succeeded. Original artifact `10036940294`, named
`batch-controller-34174908092-1`, has ZIP SHA-256
`0406d5f3b190cfc6f4dc18b46e8bae60ceef9a85aa25f9747ae82462fc95828f`.
Its result was `initialized`, with null state/request and the exact executor.
The independent GraphQL read found zero comments and a checkpoint with head
and pending null. Its editor was stable Bot `MDM6Qm90NDE4OTgyODI=`, and its
writer bound the exact repository, Issue, workflow, controller job, control,
run and attempt. Only controller `101902284120` succeeded; all three other
jobs were skipped. Initialization created neither a claim nor a tested baseline.

[Diagnostic 34175087273/1](https://github.com/endaye/lmdj/actions/runs/34175087273/attempts/1)
durably recorded observe `5577455885`, admit `5577456613`, and claim
`5577457236` before the controller completed. The fixed request was
`batch:o1-claim-cancel-live-20260908-issue857:1`, bootstrap with null base,
target equal to control, and executor `34175087273/1`. Policy digest
`bc6834ca20b75872c42c92c3e5c5ac1fcc3d515889f4544cb37aff27620ea1c6`
selected the complete sixteen-suite inventory. All three comments were authored
by the stable Bot, with null editor/lastEditedAt and complete pagination.
Their previous links and content digests were independently recomputed;
the checkpoint head was
`7baea770ba42da71500d822954edb6d5bb775ff3c206764c5ec8e3b03da9cfa9`,
pending null. Hashes establish content consistency, not independent signatures.

Controller `101902795399` succeeded and waiter `101902884628` was actually
in progress from `2026-09-08T00:59:20Z`. The original waiter log records
`Run sleep 285` at `00:59:21.0827833Z`, then the actual error
`The operation was canceled.` at `01:00:14.3120617Z`, followed by
`Terminate orphan process: pid (1895) (sleep)` at `01:00:14.3422814Z`.
Thus cancellation interrupted the live sleep after approximately 53 seconds,
well before the 285-second expiry. The log's earlier colored shell-command
preview contains the future expiry echo and `exit 1`; these are displayed
script text, **not executed expiry output**. Unlike C2, this log contains no
actual natural-expiry message or process exit-1 result before cancellation.

Independent exact-attempt API reads confirmed the whole parent and waiter
`completed/cancelled`; the actual wait step was cancelled. The four-job
inventory contained only the successful controller, cancelled waiter, skipped
legacy reporter and skipped product execution. Artifact inventory was zero.
The complete Issue GraphQL responses before and after cancellation were byte
identical, including checkpoint, editor metadata, all three records and pagination.

[Ordinary settlement 34175249441/1](https://github.com/endaye/lmdj/actions/runs/34175249441/attempts/1)
then succeeded. Original artifact `10037022559`, named
`batch-controller-34175249441-1`, has ZIP SHA-256
`e441c8a05dd529a3081992c870efbe3cf67b17476ca58f86dd11e7f266f6032d`.
The complete original three comment objects were unchanged; result `5577478685`
preceded advance `5577479369`. All five previous/digest links and the final
checkpoint were checked against the actual records, with unchanged Bot identity
and no comment editing. The original result recorded generation 5, active null,
all sixteen outcomes `missing`, and sixteen debts each at attempt 1 with
`paused=false`. Failures remained empty; no missing suite was made green or
invented as a product failure. Processed/pending were the frozen target; this
is processing progress, not tested health. The result was idle, request null,
explicitly settlement-only with no execution authorized.

[Fresh ordinary replay 34175357574/1](https://github.com/endaye/lmdj/actions/runs/34175357574/attempts/1)
succeeded with original artifact `10037052635`, named
`batch-controller-34175357574-1`, ZIP SHA-256
`58ed9a9f58735e3592006ae7c8cf29d700fb0485e340522f847419f4d7b50ca8`.
The entire replay state equalled settlement, not only its generation or debt
count. It returned idle/request null with its own exact executor identity.
The entire GraphQL response was also byte identical to settlement, retaining
all five records and metadata with no new event. Both ordinary recovery runs
had exactly four jobs: controller success and all other jobs skipped. They did
not re-admit a request, reset debt attempts or run products.

All three downloaded original ZIP hashes matched the API artifact digests.
Complete exact-attempt runs/jobs, Issue snapshots, original ZIPs and the waiter
log are retained at `/tmp/lmdj-o1-C3-independent.xeBoAb`; this is an investigation
copy, not a promise of permanent artifact retention. This closes the separately
observed running-interruption → missing-evidence settlement → idempotent replay
leg. It does not prove execution-enabled debt recovery, an exact full candidate,
remaining completion/consumer-union journeys or automatic T5/chain-limit
acceptance. It adds no claims about later product batches or reports.

For this C3 evidence-only appendix, Version impact: none — no version or release
identity is allocated. Documentation impact: none — no Portal page, source
diagram, current behavior or documented source contract changes. Verification
uses the complete original objects above, nonempty committed-range docs-static,
66 ownership tests and whitespace checks. No additional Portal build is required
for this unrelated explanatory ledger; the earlier Portal result below remains
historical rather than a claimed fresh pass.

### Automatic batch 38 and the two frozen historical candidates

This evidence-only Task uses `docs/ci-o1-auto38-candidate-evidence`, based on
`bc23b4882276c54a8e30c6f1c2e8001fc4a00eb8`. Its only declared file is this
ledger. It appends subsequent observations without changing the C3 cancellation
facts above. Root owned the actual dispatches; the independent audits and this
documentation Task performed no product execution, dispatch or journal mutation.

#### Automatic interval, complete result and settlement

[Automatic run 34175405275/1](https://github.com/endaye/lmdj/actions/runs/34175405275/attempts/1)
froze request `batch:o1-incremental-20260908-issue807:38`, base
`0c50b0a9bfbf23ed73e2357e5ff2c0d6d2850728`, target/control
`fe043fd3a2a06dfbca4088cc59e0e8ef6997f336`, and policy
`bc6834ca20b75872c42c92c3e5c5ac1fcc3d515889f4544cb37aff27620ea1c6`.
Its admission artifact `10037092682` has ZIP SHA-256
`bedffb15473ae3a56f08eee38f6b3469b9dadbfbd2adecf8aa5bb93f6b88ed15`.
Independent real Git collection found nine first-parent commits and 27 changed
paths, including the actual intervening CI changes rather than only the two
Host documentation changes. The ten historical policy reads (base plus each
commit) had the same digest. The deterministic floor already selected all
sixteen suites; authenticated partial review suggestions did not reduce it.
The journal held one claim for this executor, not a heavy run per intervening PR.

The parent completed with `failure` at the terminal API observation updated
`2026-09-08T02:01:09Z`. Original artifact `10038089553`, named
`batch-verdict-fe043fd3a2a06dfbca4088cc59e0e8ef6997f336-34175405275-1`,
has ZIP SHA-256
`b0e679ce9044af673601c363a385bce5bca8600709c023de1775e9fdbd22492e`.
Its three original members are `needs.json`, `execution.json`, and `verdict.json`.
The independent audit used the actual Runtime result consumer with GET-only
API access, exact source/module parity, historical policy, complete terminal
job observations and the original artifact. It accepted a complete full-scope
result: fourteen suites passed; `ci_contract` and `creator` failed. Both stress
suites, including `core_tsan_stress`, passed. No suite was missing, blocked,
cancelled or infrastructure-classified. This is **not** an all-passed candidate.

The CI contract failure occurred before Python tests: actual actionlint invoked
ShellCheck and rejected an unused TSan preflight loop variable. Its later repair
does not recolor this frozen result. The Creator failure remains a separate
observed suite failure; this appendix does not infer its root cause.

[Settlement 34178674753/1](https://github.com/endaye/lmdj/actions/runs/34178674753/attempts/1)
returned idle with `settlement-only; no execution authorized`. Original artifact
`10038132907` has ZIP SHA-256
`0729f4446b25547c3d5cc87337c28b29dd3fcc79d4e588ae00b4026b73bb7b63`.
The authenticated state reached generation 45 with processed `fe043fd3…`,
pending `bc23b488…`, active null and both explicit candidate IDs still queued.
The new result preceded advance. Debt became empty because the previous TSan
verification debt was actually covered; the seven historical failure records
remained, including the new CI contract and Creator failures. Zero debt means
no missing verification at this boundary, not an overall green project.

#### Old candidate rejected before heavy work

Candidate `o1-full-candidate-0fedd-20260908-01` retained its original target
`0fedd7268e5f0f9a27390c3d8085387083f46e86`, control `fe043fd3…`, policy
`bc6834ca…ea1c6` and origin `34175608688/1`. Its actual executor was the
different fresh [run 34179012035/1](https://github.com/endaye/lmdj/actions/runs/34179012035/attempts/1)
under `bc23b488…`. Controller `101914073664` succeeded; Change Scope
`101914263082` failed at `02:09:36Z` with the actual diagnostic that the batch
workflow sources were incompatible or unavailable. The log's displayed script
also contains a later candidate-policy check; that preview is not evidence the
later check executed. The observed rejection was the earlier source check.

The complete 28-job inventory had one success, one failure and 26 skips. The
only artifact was admission `10038242350`, ZIP SHA-256
`2311a75f44086d77f89910086b3c5f0defcf1d18e492aa1cd1b960cbb41b239e`;
there was no scoped verdict or product execution. The old request was retained,
not silently rewritten under the new control. Its later ordinary terminal
settlement recorded all sixteen selected outcomes as `missing`, then advanced
only its explicit queue slot. It did not rewind automatic processed progress,
create automatic debt for the older candidate or clear newer failure records.

#### Second candidate admitted; completion and reporting still pending

[Run 34179165063/1](https://github.com/endaye/lmdj/actions/runs/34179165063/attempts/1)
settled the first candidate and admitted
`o1-full-candidate-0fedd-20260908-02`. This second request retained the same
exact historical target `0fedd726…`, but its own frozen control
`bc23b4882276c54a8e30c6f1c2e8001fc4a00eb8`, policy
`874064884b84235f6e8337369001923975a6e63742308728bd9bedfa10ace961`
and origin `34177534122/1`. Its full sixteen-suite selection was not replaced
by newer automatic pending work. Original admission artifact `10038301423`
has ZIP SHA-256
`c0bab42f2a65d416b75ebf65904464edb053ca785fd8b8161729829dc5fd66fd`.
Change Scope `101914786412` succeeded and product jobs actually started; this
is stronger than a queued request but is not a completed candidate result.

Independent full journal authentication reached generation 51: events 45/46
admitted and claimed candidate 01, 47 persisted its missing result, 48 advanced
it, and 49/50 admitted and claimed candidate 02 for executor `34179165063/1`.
Both checkpoint reads agreed on head
`bd8814b2fbb6b1134dfa296cf026a6568b2fcf9c7f8dc267cf28343ac8ba60fd`.
The audit checked every actual writer/run/attempt/workflow/source/main-history
binding, author/editor rules and digest chain, then independently replayed the
whole state equal to the admission artifact. Hashes alone were not treated as
writer identity. All previous requests were unchanged; queue was empty and
active named only candidate 02. Processed `fe043fd3…`, empty debts and all seven
failure records were byte-for-byte equivalent to automatic batch 38 settlement.

At the `2026-09-08T02:17Z` read-only observation, candidate executor
`34179165063/1` and report run
[34179303196/1](https://github.com/endaye/lmdj/actions/runs/34179303196/attempts/1)
were both `in_progress` with no conclusion. This appendix claims neither a
passed candidate nor completed report delivery. The execution-enabled C3 debt
recovery, remaining O1 journeys, and T5/O2 activation remain separate unfinished
boundaries; no version or release operation is implied.

Raw original evidence is retained in
`/tmp/lmdj-o1-auto38-independent.WONv4M`,
`/tmp/lmdj-auto38-root-settle.FoeenZ`,
`/tmp/lmdj-auto38-settle-audit.XF7TvO`,
`/tmp/lmdj-o1-candidate1-independent.ZBziSO`,
`/tmp/lmdj-candidate2-root-admit.840Tg1`, and
`/tmp/lmdj-candidate2-admit-audit.tVHxqQ`. These are investigation copies, not
permanent platform-retention guarantees. This Task cross-checked original ZIP
digests, complete states and the live exact-attempt identities; local fixtures
were not substituted for the observations.

Task verification: staged ownership, nonempty-range docs-static and whitespace
checks are recorded with the final PR. Version impact: none. Documentation
impact: none — only explanatory evidence is added; no Portal page, diagram,
tooling, projected identity or documented product source fact changes. Under
the current Task-scoped policy, no fresh Portal run is required or claimed;
the historical result below is unchanged. Pitfall impact: none — existing
whole-journey, failure visibility and exact-source guidance is applied.

### Three completed report rounds after automatic batch 38

This subsequent evidence-only Task uses `docs/ci-o1-report-delivery-evidence`
from `3903e122c511bd9ea6df4ce63891d49cec9309f0`. Its only declared file is
this ledger. The entire earlier ledger is preserved, including the accurately
timed observation that the first report was still running at 02:17Z. The
following actual terminal evidence extends that observation; it does not
rewrite it or claim a result for the still-running second candidate.

Root dispatched the three report rounds. Independent Codex audit
`scheduler_storage_probe` authenticated their actual Issue transport, complete
pagination, writer/run/attempt/workflow/source and author/editor identities,
checkpoint/digest chain and pure outbox replay. This documentation Task also
recomputed all three complete reducer states, compared original prefixes and
both terminal reads, and matched the twenty newly delivered business receipts
below to the actual retained HTTP objects. These evidence checks performed no
remote mutation and did not redispatch reports.

| Actual report run (attempt 1) | Frozen control | Terminal API update (UTC) | Outbox generation | Delivery state after the round |
| --- | --- | --- | --- | --- |
| [34179303196](https://github.com/endaye/lmdj/actions/runs/34179303196/attempts/1) | `bc23b4882276c54a8e30c6f1c2e8001fc4a00eb8` | 2026-09-08 02:19:32 | 58 → 93 | 24 queued identities in total: 23 delivered, 1 still queued |
| [34179870307](https://github.com/endaye/lmdj/actions/runs/34179870307/attempts/1) | `3903e122c511bd9ea6df4ce63891d49cec9309f0` | 2026-09-08 02:31:29 | 93 → 128 | 32 queued identities in total, all delivered |
| [34180577915](https://github.com/endaye/lmdj/actions/runs/34180577915/attempts/1) | `3903e122c511bd9ea6df4ce63891d49cec9309f0` | 2026-09-08 02:38:04 | 128 → 136 | 34 queued identities in total, all delivered |

All three actual parents and their `Incremental batch controller` jobs
completed successfully. Each complete four-job inventory had the legacy
reporter, product execution and cancellation waiter skipped. Reporting did
not run or rerun products. Success alone was not taken as delivery proof:
each round's complete terminal Issue snapshot equalled its independent reread,
and the authenticated records and frozen payloads from previous rounds remained
unchanged.

The three checkpoint heads, each with pending null, were respectively:

- generation 93: `ccf48bac06407547dbcb7b32dac294b22cdfbebbc9bc71afa977b6ffadd1d5b7`;
- generation 128: `324600ddfc6b6aa1bc8e36678ed21b52174eed9ceb6a3e1b768f9962544d8325`;
- generation 136: `e724d6166206f08bf1a50e7a0dfea57ec4f3e0d08caa583153e4c209e6e30003`.

The first two rounds each appended eight queue events and nine complete
claim/ack/delivered sequences, including one already-queued review observation.
The final round appended two queue events and two complete delivery sequences.
The resulting twenty new deliveries were:

- Automatic batch 38's CI contract failure: existing
  [Issue 820 comment 5578078418](https://github.com/endaye/lmdj/issues/820#issuecomment-5578078418).
  Its Creator failure: existing
  [Issue 865 comment 5578082869](https://github.com/endaye/lmdj/issues/865#issuecomment-5578082869).
  Both frozen bodies identify request 38, exact target/control `fe043fd3…`,
  executor `34175405275/1`, policy and actual failed suite. They retain failure
  evidence even though a later code repair may exist.
- Sixteen separate missing-verification suite buckets for candidate
  `o1-full-candidate-0fedd-20260908-01`: Issues 874–879 and 881–890. These are
  the complete canonical selected inventory, not sixteen inferred product
  failures. Each actual Issue body, label set and assignee matches the frozen
  outbox payload and retains the old candidate's target `0fedd726…`, control
  `fe043fd3…`, executor `34179012035/1` and missing evidence classification.
  The sixteen suites map in canonical order to chameleon_lab, ci_contract,
  core_asan, core_coverage, core_macos, core_release_stress, core_tsan_stress,
  core_ubuntu, creator, deploy_contract, docs_static, package, portal,
  web_runtime_host, web_runtime_lab and web_toolchain.
- Two older, already-queued review observations were delivered to
  [Issue 819 comment 5578114527](https://github.com/endaye/lmdj/issues/819#issuecomment-5578114527)
  (PR 805, review run `34154919386/1`) and
  [comment 5578212206](https://github.com/endaye/lmdj/issues/819#issuecomment-5578212206)
  (PR 806, review run `34155139978/1`). Their exact frozen comment bodies and
  Issue targets were checked against the actual HTTP receipts; they were not
  replaced with new observations or another AI review.

At generation 136, all **34 already-queued observations** were delivered, with
no queued or claimed-but-unresolved entry in that snapshot. This is not a claim
that every possible source has been discovered, that every future candidate
result is already reported, or that a later unknown POST can be blindly retried.
Candidate 02 was still executing at this evidence boundary; no all-passed
candidate, C3 execution-enabled recovery, T5/O2 activation or release is claimed.
The scheduler's failed/missing outcomes are not recolored by successful delivery.

Complete original API objects, authenticated journal records, reducer states,
two-read snapshots and exact business receipts are retained in
`/tmp/lmdj-o1-report38-independent.tM9Urs`,
`/tmp/lmdj-o1-report38-tail-independent.jo4FiI`, and
`/tmp/lmdj-o1-report38-final-independent.GB8MPT`. These investigation copies do
not extend GitHub artifact retention or constitute independent signatures.

Task verification: complete retained-state and twenty-receipt assertions,
staged ownership, cached whitespace and nonempty committed-range docs-static;
the final PR records their results. Version impact: none — no version identity
or release operation. Documentation impact: none — only historical evidence,
not a Portal page, diagram, tooling, projected identity or documented product
source fact. No fresh Portal run is required or claimed under the current
Task-scoped policy. Pitfall impact: none — existing complete-journey and exact
receipt guidance applies; this appendix introduces no new protocol or process.

### Candidate 02: full result, canonical acceptance and isolated settlement

This evidence-only Task uses `docs/ci-o1-candidate2-complete-evidence`, based on
`77e84e086298430d94be9135929a5ebdac1eba17`. Its only declared file is this
ledger. All earlier bytes remain unchanged, including the earlier correctly
timed pending observations. These evidence checks did not execute products,
redispatch a workflow, write a journal or perform a release operation.

[Candidate executor 34179165063/1](https://github.com/endaye/lmdj/actions/runs/34179165063/attempts/1)
actually completed with success; its terminal API record was updated at
`2026-09-08T03:02:16Z`. The request remains
`o1-full-candidate-0fedd-20260908-02`, with origin `34177534122/1`, null base,
target `0fedd7268e5f0f9a27390c3d8085387083f46e86`, control
`bc23b4882276c54a8e30c6f1c2e8001fc4a00eb8`, and policy
`874064884b84235f6e8337369001923975a6e63742308728bd9bedfa10ace961`.
Original artifact `10039248329`, named
`batch-verdict-0fedd7268e5f0f9a27390c3d8085387083f46e86-34179165063-1`,
has ZIP SHA-256
`424442acd3b1f3183b6344f43bf707c07c829ae8a480f1fdd7e89d6e987c29c2`.
The complete original `needs.json`, `execution.json` and `verdict.json` bind
that exact request. All sixteen canonical selected suites passed, including
both stress suites. Verdict evidence digest is
`ac2112426f2f0e06ff82b97c535a2f487ec1436acc1b5c4e64023180121b083b`.
No missing, blocked, infrastructure or unselected suite was substituted for pass.

Root ran the actual canonical `BatchEvidenceConsumer.verify_run` complete
verification, with actual GET responses and the original origin/admission/verdict
artifacts. It returned `canonical-consumer-accepted`, status passed, executor
success and `release_authorized=false`. The origin attestation artifact
`10037779077` has ZIP SHA-256
`c6d33219f9db37aef526a459368fa6f51b2c1a5c039544e999073a7f1c085b7c`;
the admission artifact `10038301423` retains the earlier recorded
`c0bab42f…d66fd` hash. This consumer verifies the original durable-claim
attestation; it does not use the latest journal replay as a replacement claim
proof. Its reference retains origin/admission record digests, executor event,
policy, target and evidence digest.

The audit recorded local consumer head
`eea13220a1b62b1aaf88b350afffe3e722f10a5b` and actual main
`77e84e086298430d94be9135929a5ebdac1eba17`. This Task independently compared
the consumer and imported evidence-validation/protocol source blobs against
that actual main and found byte equality; it did not silently certify a newer
unreviewed consumer. The canonical accepted verdict also equals the separately
downloaded independent verdict in full, not only its pass count.

[Ordinary settlement 34182221147/1](https://github.com/endaye/lmdj/actions/runs/34182221147/attempts/1)
then completed successfully under control `77e84e08…`; terminal API update was
`2026-09-08T03:05:35Z`. Original controller artifact `10039310386` has ZIP
SHA-256 `cacaec1f35821cfbadc7f5b10ba194e7c28786bd82a824054a51b2dbc57a46f2`.
Independent Codex audit `scheduler_storage_probe` authenticated the complete
actual transport/writer/source/editor evidence, replayed all 54 events, and
compared the whole state to the original controller artifact. The original
51 complete comment objects were unchanged. The only additional events were
51 observe, 52 result and 53 advance; result preceded candidate-slot advance and retained
all sixteen passed outcomes for this exact executor and candidate.

Both full GraphQL reads were byte identical (SHA-256
`136422c1b5faeef1d58a39595e7dedb97385b103cc36f56cf406a76fa0b4f8f4`),
with checkpoint head
`762f0cd5f2dfdafe82995f4e62ae92eb265d4cc2837713d574f3e19cfa422414`
and pending null. The result was idle/request null, active null and queue empty;
all four jobs were terminal, only the controller succeeded and the other three
were skipped. Automatic processed remained the newer `fe043fd3…`; its empty
debts and all seven failure objects were unchanged. Existing requests and
recovery-request state were also unchanged. Pending observed main `77e84e08…`
without treating it as tested. A passed historical candidate did not rewind
automatic progress or erase newer defects.

The accepted original evidence and GET inventory are retained in
`/tmp/lmdj-candidate2-canonical-accepted-34179165063`; the independent terminal
run/jobs and original verdict ZIP are in
`/tmp/lmdj-candidate2-terminal-independent.xtnd1f4b`. Complete before/after
settlement evidence is in `/tmp/lmdj-o1-candidate2-settle-independent.pyPfZO`
and `/tmp/lmdj-o1-candidate2-postsettle.qXvFeh`. The actual verdict artifact
expires at `2026-10-08T03:02:12Z`; local copies do not extend platform retention
or waive freshness and source checks at any later use.

This establishes an actual complete accepted candidate only for fixed target
`0fedd726…`, not current-main full health. It does not establish C3 execution-
enabled debt recovery, T5/O2 activation, or a successful future report. No
release intent, tag, Release, version allocation, deployment or publication
was created. Those remain separate boundaries.

Task verification: original candidate/verdict and settlement identity checks,
source-blob equality, actual retained-state/prefix/two-read assertions, staged
ownership, whitespace and nonempty committed-range docs-static. The final PR
records results. Version impact: none — evidence-only, no identity allocation.
Documentation impact: none — no Portal page, diagram, tooling, projected
identity or documented product source fact changes. No new Portal run is
required or claimed. Pitfall impact: none — existing complete-evidence and
historical-candidate isolation rules applied; no implementation changed.

## Ledger verification

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

## C3 execution-enabled recovery, settlement, replay and reporting

This evidence-only Task uses `docs/ci-o1-c3-recovery-evidence`, based on
`3c2211c8336791956107aa67fe4ff9f1e40b3944`. Its only declared file is
`docs/plans/2026-09-08-lmdj-ci-incremental-o1-evidence.md`. All preceding
historical text is retained byte-for-byte, including the earlier C2 expiry race
and the separate C3 real interruption proof. The following observations extend
that proof through real recovery execution, settlement, fresh replay and final
failure reporting. They do not declare all O1 scenarios or T5/O2 complete.

### Preserved debt and a real execution-enabled admission

The authenticated pre-admission snapshot of isolated scheduler Issue 857,
epoch `o1-claim-cancel-live-20260908-issue857`, was generation 5 with no active
request. Processed and pending both remained
`fe043fd3a2a06dfbca4088cc59e0e8ef6997f336`. All sixteen suites retained
`missing` debt with attempt 1, paused false, and the exact reference
`missing:batch:o1-claim-cancel-live-20260908-issue857:1`; failures were empty.
That was missing verification following cancellation, not sixteen product bugs.

[Recovery run 34182418092/1](https://github.com/endaye/lmdj/actions/runs/34182418092/attempts/1)
retained request `batch:o1-claim-cancel-live-20260908-issue857:6`, kind `auto`,
base `fe043fd3a2a06dfbca4088cc59e0e8ef6997f336`, target/control
`77e84e086298430d94be9135929a5ebdac1eba17`, and policy
`874064884b84235f6e8337369001923975a6e63742308728bd9bedfa10ace961`.
Original controller artifact `10039362368` has ZIP SHA-256
`a609d7b1d202f9b8b90b402a20d1e1ea4baaeabbd3e8a7fa2ff84c63a572e4d5`.
Its action was `execute`, and generation 8 contained the exact executor and
claim `34182418092/1`. The original missing result and all sixteen debt objects
remained unchanged at admission; a claim was not mistaken for coverage.

Independent Git/policy selection already required full sixteen-suite coverage
for the intervening changes. The actual request also recorded
`carry executable verification debt`. Thus this admission exercises debt
carriage with a genuinely full interval; it is not evidence that debt alone
upgraded an otherwise none/focused selection. Incomplete review suggestions did
not reduce the deterministic floor. Root authenticated the pre-state and
original admission; the independent read-only audit subsequently authenticated
all eight scheduler records and replayed the same generation-8 state. The
documentation Task also checked the original ZIP digest and retained identities.

Evidence copies: `/tmp/lmdj-C3-debt-before-auth.1gf4hvnh`,
`/tmp/lmdj-C3-debt-admission-auth.0r0dathi`, and
`/tmp/lmdj-o1-C3-report-before.JtCygm`. These are local investigation copies,
not permanent artifact-retention guarantees or independent signatures.

### The original cancelled execution's sixteen missing observations delivered

While that recovery was not yet settled, ordinary reporting used scheduler 857
and the existing outbox 817, without initializing either journal or executing
products. The actual pure report projection of the authenticated scheduler
produced exactly sixteen observations from the original settled request `:1`,
executor `34175087273/1`, target/control `fe043fd3…`, historical policy
`bc6834ca…ea1c6`, and evidence digest
`9acf943399cec02f748ba96fd4e1164490075ea5f38f9b520ad2768f4ab8457a`.
The active recovery `:6` had no result and contributed no report. The later
documentation/policy migration did not replace the original result's policy.

| Report run (attempt 1) | Control | Terminal API update (UTC) | Outbox generation | Original cancellation observations delivered |
| --- | --- | --- | --- | --- |
| [34183541684](https://github.com/endaye/lmdj/actions/runs/34183541684/attempts/1) | `3c2211c8336791956107aa67fe4ff9f1e40b3944` | 2026-09-08 03:34:29 | 136 → 168 | First 8 of 16; remaining 8 not yet queued |
| [34184208131](https://github.com/endaye/lmdj/actions/runs/34184208131/attempts/1) | `3c2211c8336791956107aa67fe4ff9f1e40b3944` | 2026-09-08 03:45:39 | 168 → 200 | All 16 of 16 delivered |

Each run completed successfully with only its controller successful and all
three other jobs skipped. The reporting limit remained 8 and the controller
timeout was not increased. Each round added exactly eight
queue → claim → ack → delivered sequences. Actual HTTP comment bodies matched
both the frozen outbox payload and the precomputed original-result report:

| Suite | Actual receipt |
| --- | --- |
| chameleon_lab | [874 / 5578661263](https://github.com/endaye/lmdj/issues/874#issuecomment-5578661263) |
| ci_contract | [875 / 5578667273](https://github.com/endaye/lmdj/issues/875#issuecomment-5578667273) |
| core_asan | [876 / 5578673062](https://github.com/endaye/lmdj/issues/876#issuecomment-5578673062) |
| core_coverage | [877 / 5578679482](https://github.com/endaye/lmdj/issues/877#issuecomment-5578679482) |
| core_macos | [878 / 5578685765](https://github.com/endaye/lmdj/issues/878#issuecomment-5578685765) |
| core_release_stress | [879 / 5578692107](https://github.com/endaye/lmdj/issues/879#issuecomment-5578692107) |
| core_tsan_stress | [881 / 5578698385](https://github.com/endaye/lmdj/issues/881#issuecomment-5578698385) |
| core_ubuntu | [882 / 5578705891](https://github.com/endaye/lmdj/issues/882#issuecomment-5578705891) |
| creator | [883 / 5578771262](https://github.com/endaye/lmdj/issues/883#issuecomment-5578771262) |
| deploy_contract | [884 / 5578778770](https://github.com/endaye/lmdj/issues/884#issuecomment-5578778770) |
| docs_static | [885 / 5578785567](https://github.com/endaye/lmdj/issues/885#issuecomment-5578785567) |
| package | [886 / 5578791734](https://github.com/endaye/lmdj/issues/886#issuecomment-5578791734) |
| portal | [887 / 5578798105](https://github.com/endaye/lmdj/issues/887#issuecomment-5578798105) |
| web_runtime_host | [888 / 5578804521](https://github.com/endaye/lmdj/issues/888#issuecomment-5578804521) |
| web_runtime_lab | [889 / 5578810290](https://github.com/endaye/lmdj/issues/889#issuecomment-5578810290) |
| web_toolchain | [890 / 5578816442](https://github.com/endaye/lmdj/issues/890#issuecomment-5578816442) |

Independent audits authenticated all historical writer/run/attempt/workflow,
source/main-history and author/editor bindings, full pagination, checkpoint and
digest chain, then replayed the outbox. The first round retained all original
136 complete comment objects; the second retained all 168. Each round's complete
two-page terminal snapshot equalled an independent reread byte-for-byte. Root
separately checked the retained prefixes, both snapshots and all sixteen actual
receipts against the planned/frozen bodies.

The generation-168 head was
`956485c5b6eebfd9b19cd4458306eb5574c147ba2d0c86db6aa59041719d0006`;
generation 200 was
`b2c1342c63b5f00efc6397f14be2efb05fe6902a020956198865d7860b133d38`.
Both checkpoint pending fields were null. At generation 200 all fifty already
queued observations were delivered; this includes earlier unrelated observations,
not fifty C3 failures. It does not mean every future source is discovered or
reported, nor does report success clear scheduler debt or prove product health.

Complete evidence is retained in `/tmp/lmdj-o1-C3-report-round1.oOlGfC` and
`/tmp/lmdj-o1-C3-report-round2.0sBGQe`. The latter's complete snapshot SHA-256 is
`991e8c176773aeb40172fa1873fec3f59d1293d158474cf651bc4b046071311e`.

### Complete recovery result, ordinary settlement and fresh replay

Recovery executor `34182418092/1` completed with `failure` at the terminal API
observation updated `2026-09-08T04:01:52Z`. The complete actual inventory had
30 jobs. Original scoped verdict artifact `10040353988` was 4,711 ZIP bytes,
SHA-256 `2f08cd256d1b11a4e1e52bce66e6a57a0db81dd3361c1dcd15fd62ff789a16fb`,
with evidence digest
`63c8a24d690c0f0dc6cf695b90c3a0953129cf3205c6be0aa04c143070ece4f7`.
All sixteen suites had verification debt false: fifteen passed, and only Creator
failed. Both stress suites, sanitizers, coverage and package passed. Producer
`101932955121` successfully judged and uploaded the original scoped evidence;
its final visibility step retained the actual failed outcome. No missing or
blocked selected suite was disguised as a pass.

Independent GET-only `Runtime.result_for` accepted the original
`execution.json`, `needs.json` and `verdict.json` against the frozen request,
historical policy and actual terminal jobs. Root separately inspected the original
ZIP and result. This documentation Task checked the same ZIP byte length/digest
and complete suite outcomes. Evidence copies are
`/tmp/lmdj-C3-terminal-independent.uvp4iziv` and
`/tmp/lmdj-C3-root-verdict.2E3z6O`. A full-scope result containing a failure is
not an all-passed release candidate.

[Ordinary settlement 34185676231/1](https://github.com/endaye/lmdj/actions/runs/34185676231/attempts/1)
used control `557019405e1ef833d4750e9411f83a92e492c7cf` and succeeded.
Controller artifact `10040411432` has ZIP SHA-256
`fde6e1fd0d0157c7e875b14650398974f6a05dd1b84359bed467ae4b56f5763d`.
The authenticated journal retained all original eight envelopes, then appended
generation 8 observe, 9 result, and 10 advance, reaching generation 11.
Its anchored head was
`d379f0af88f1e725efb305dbe73954f98ddde4d88353a7d55ae3fd2386a9f2fa`,
with checkpoint pending null. Processed advanced to the frozen execution target
`77e84e086298430d94be9135929a5ebdac1eba17`, while scheduler pending reflected
newer main `ed42b46faa539f0ead8c161d5ee54b70b2193c40`. Active became null,
debt became empty because every selected suite had actual coverage, and the
single Creator failure was retained at the exact target. `history_unknown`
remained true; neither coverage nor a new checkpoint invented earlier history.

[Fresh settlement replay 34185995655/1](https://github.com/endaye/lmdj/actions/runs/34185995655/attempts/1)
used control `ed42b46faa539f0ead8c161d5ee54b70b2193c40`, succeeded, and retained
artifact `10040509790`, ZIP SHA-256
`d0bba114d72729658d637d1c9c39db5af65e7a76b28dcf6396d010120206fa64`.
Both original artifact states equalled the complete independently authenticated
settled state. The replay's two complete chain and anchor reads also agreed,
with no new event, generation, debt or failure. Both operations returned idle
without a request; this was settlement-only replay, not a claim that a fresh
execution-enabled reconcile had no remaining main work. No product job ran in
either operation.

The documentation Task independently repeated the original eight-envelope
prefix, both artifact-state equalities, whole-state replay equality and complete
chain/anchor equality assertions from
`/tmp/lmdj-C3-settle-independent.wx08lgj5` and
`/tmp/lmdj-C3-replay-independent.3g_e_6zo`. The independent runtime audit and
root checked full journal authentication; hashes were not used as signatures.

### The recovery's actual Creator failure delivered without duplicate missing reports

[Report run 34186045987/1](https://github.com/endaye/lmdj/actions/runs/34186045987/attempts/1)
used control `ed42b46faa539f0ead8c161d5ee54b70b2193c40` and succeeded.
Controller `101934467376` succeeded; all three other jobs were skipped.
The outbox retained all 200 earlier complete comment objects and all fifty
existing delivery objects, adding only one queue → claim → ack → delivered
sequence. The original cancellation's sixteen observations were not reposted.

The new exact observation
`batch/f613c3552b39ec4d6ad6d03da89228680f183605d7cdb18a987f2b9f356bd1d1`
was delivered to existing
[Issue 865 comment 5579060281](https://github.com/endaye/lmdj/issues/865#issuecomment-5579060281).
Its actual stable-Bot HTTP comment body equalled both the frozen payload and the
actual reporter's pure projection of settled request `:6`, executor
`34182418092/1`, target `77e84e08…`, and its original failed verdict. This is
a product/test failure observation with no verification debt, distinct from
the earlier missing-verification reports. No Issue was automatically closed.

Full historical writer authentication, all three comment pages, checkpoint and
digest chain, and pure outbox replay reached generation 204 with all 51
already-queued observations delivered. Head was
`3b32b21990e05a542cfab0bbb9209514351c17fe7bf875dd62e9a0ae0173eb49`,
checkpoint pending null. Both complete terminal snapshots were byte-identical.
The original 200-comment prefix and fifty delivery objects were checked in full,
not only by count. Evidence is retained in
`/tmp/lmdj-o1-C3-final-report.br7HM7`, including actual HTTP receipt, projected
report, authenticated records, replayed state and original run/job/log snapshots.

This completes the recorded C3 path from retained cancellation debt through
actual selected execution, coverage-aware debt settlement, stable fresh replay
and failure delivery. It does not prove current main is full-green or globally
caught up: newer pending work remains, Creator failed, historical unknown status
remains, and T5/O2 authorization and actual automatic-chain recovery are separate.
No version, release, deployment, additional dispatch or product execution was
performed by this documentation Task.

Task verification: complete retained-evidence and old-ledger-prefix assertions
passed, alongside the 66 ownership tests and whitespace checks. Nonempty
committed-range docs-static from base `3c2211c8336791956107aa67fe4ff9f1e40b3944`
passed after the local commit; an empty pre-commit range was not counted.
Version impact: none — no version or release action.
Documentation impact: none — explanatory evidence only, not Portal pages,
diagrams, tooling, projected identities or documented product source facts.
No fresh Portal run is required or claimed. Pitfall impact: none — existing
complete-journey and exact-receipt guidance applies; no new protocol or gate.
