# Daily CI simplification

Relates to #1996. Owner direction (2026-10-11): refresh the updated repository,
make an implementation plan and begin optimization. Ordinary development should
use small, change-related checks; complete verification belongs to an exact
candidate or an explicit full request. This is not release authorization.

## Refreshed premises

Base and task worktree: `8769907ea75320f051d43707301af5188c0f0086`.
Fetched again after the owner's repository-update notice; main was unchanged.
Read #1996, #1955 and their comments, successors and owning source at this base.

| Original premise | Disposition and evidence |
| --- | --- |
| 14 local lanes / 16 complete suites | Superseded: #1997 (`305b7660`) removed the retired Chameleon lane. `local_lanes.json` now has 13 lanes; `self_test_policy.json` has 15 suites. Do not repeat the deletion. |
| T2 always adds full | Delivered by #1957 (`c1ce1e30`); `review_pipeline.py` supplies no additional scope. #1955 retains observed batch evidence; its open state is not missing implementation. |
| Selected local lanes run complete proofs | Outstanding: `local_lanes.json` still calls full Core/Web proofs and complete CI/deploy contracts; `local_preflight.py` still enforces batch-only evidence. |
| Every PR edit repeats source verification | Outstanding: `pr-contract.yml` subscribes to `edited`; every selected source job shares the same admission as source events, and its concurrency group cancels the previous run. Positive control: `synchronize` also reaches those jobs. |
| Web proof can simply lose its second build and browser steps | Rejected: reproducibility and complete browser journeys have distinct evidence. #1993 (`05e5ac06`) additionally puts deployment-fixture freshness in Creator proof. A quick/full split must retain that consumer when its inputs change. |
| Skipping a Portal job is invisible to review | Rejected: `review_wait.portal_gate` requires the latest exact-head check named `Architecture Portal provenance` to succeed. A new skipped check with that name would mask the actual result. |

Historical timing samples in #1996 show cost, not a current baseline. No new
full suite is required just to measure this plan. Each optimization records its
own changed workload and measured execution; a normal-workday before/after
sample remains final acceptance work, with sample count and cold/warm state.

## Sequence

Each task is one reviewable Conventional Commit. Re-resolve current main and
freeze exact files before each task. Ship usable increments; a future policy
does not override the live batch-evidence or candidate-verification contracts.

### T0 — Stop repeating source tests for PR metadata edits (first delivery)

Declared files:

- `.github/workflows/pr-contract.yml`
- `tests/build/ci_workflow_topology_test.py`
- `tests/build/ci_review_wait_test.py`
- `apps/docs-site/docs/operations/testing-and-proof.mdx`
- `.agents/pitfalls/skipped-job-name-retains-expression.md` (added after the
  real-event observation below, before the follow-up edit)
- this plan

Only an `edited` event whose nonempty `changes` object contains exclusively
`title` and/or `body` selects metadata-only work. Opening, synchronization,
reopening, ready-for-review, base edits, missing or unknown changes keep source
verification. Always run the existing scope and documentation-impact checker;
it fetches the actual body and checks the exact head. The metadata path avoids
CI contract, static source diff and Portal rebuild jobs.

Give edited runs their own run-specific concurrency group: neither a metadata
edit nor an earlier retarget edit may cancel a running source verification.
Ordinary source events retain their existing cancellation group. No changes to
lane inventories, assertions, timeouts, protection or full-batch execution.

The skipped Portal job on metadata events has a distinct display name. It is
not a successful provenance check and cannot replace, mask or manufacture the
real named check. Missing/failed real provenance still prevents generated-only
review eligibility. Do not relax the review consumer.

Lowest-tier verification:

- Execute the workflow's actual inline event classifier with metadata,
  source, retarget, missing and unknown payload cases.
- `python3 tests/build/ci_workflow_topology_test.py`: event-to-job wiring and
  concurrency separation. Defect caught: an edit silently reruns or cancels
  source tests, or a base change skips them.
- `python3 tests/build/ci_review_wait_test.py`: independent consumer evidence
  tests. Defect caught: a skipped metadata check masks a failed real check or
  grants provenance without one.
- `python3 tests/build/ci_local_preflight_test.py`: existing PR lane visibility.
- `python3 tests/build/ci_pitfall_ledger_test.py`: validate the observed platform
  recurrence and its UTC occurrence date.
- Pinned actionlint, `scripts/docs-site.sh check`, and staged new-path ownership
  (`python3 tests/build/ci_change_scope_test.py`). No new required status.

Far-side live acceptance: after opening the PR, edit its actual description;
record the new run's skipped source jobs and executed impact checker, and
confirm the original source run was not cancelled. A local payload test is not
this platform evidence. If unavailable, keep the acceptance gap explicit.

Initial live proof on `8c389642`: run `38096694071` completed successfully after
a real PR #2009 body edit. Scope and Documentation impact ran; all three source
jobs skipped. Original source run `38096650098` remained running, with real
Portal provenance successful. GitHub retained the unexpanded name expression
for the skipped Portal job; the follow-up consumer fixture uses that actual
string, not an assumed evaluated alias. Final-head review and source results
still need their own verification.

### T1 — Add explicit local quick verification and separate its evidence

Implementation base refreshed to `deb95de722b845d708371e90bcac138ae5e25e01`.
T0 is merged (#2009); its final-head PR Contract run `38096931869` completed
successfully, including CI contract and Portal. T1 remains outstanding: the
current parser has no profile option and the lane loader accepts only the full
commands. The existing `--lanes` filter is the positive control for command
selection; it does not change a selected lane's workload.

T1 declared files are `scripts/local-ci.sh`,
`scripts/ci/local_preflight.py`, `scripts/ci/local_lanes.json`,
`tests/build/ci_local_preflight_test.py`,
`apps/docs-site/docs/operations/testing-and-proof.mdx`, and this plan.
The real native run additionally declares
`.agents/pitfalls/shared-host-tmp-staging-permissions.md` to retain the observed
root-owned temporary staging collision, with ledger and staged ownership checks.
Add explicit `--profile quick|full` with full still the default until T3.
Initial quick overrides provide native Dev compile/unit/component feedback and
Creator UI build/unit/offline feedback; all other entries retain their full
commands until their T2 dependencies are audited. This advisory development
subset is not the final daily merge contract. T2 must add affected complete
journeys and risk selection before T3 changes any obligation.

Execution-cache identity binds profile, source/commands and the resolved local
toolchain. Keep source-bound full batch receipts separate so a macOS receipt
can still be checked from Linux; a local toolchain hash is a cache boundary,
not a requirement for the verifier to impersonate the execution host. Quick
prints `quick-pass`/`cached-quick-pass`, never a full receipt, and the old
full-evidence checker rejects explicit quick mode. Record timings for each
actually executed command, including a failing command, and none for cache hits.

Primary files: `scripts/local-ci.sh`, `scripts/ci/local_preflight.py`,
`scripts/ci/local_lanes.json`, `tests/build/ci_local_preflight_test.py`, and
this plan. Add per-command timing with no extra service. Reuse the canonical
path selector and existing test entry points. Keep full commands available;
quick successes cannot emit full-lane `pass key=` receipts. Keys bind profile,
inputs and relevant toolchain identity. Missing toolchains remain unverified.

Freeze the quick command inventory after checking the actual public boundary
tests: compile/typecheck, unit/component and affected host/contract tests.
Do not substitute `core.sh test dev fast` for persistence or concurrent
lifetime verification. Unknown dependencies retain conservative selection.
Initially make quick explicit until T3 updates the merge consumers together.

Lowest-tier tests: planner command selection, profile-separated cache keys,
input invalidation, quick/full evidence rejection, missing dependencies and
unchanged full inventory. Defects caught: stale/full-mislabelled evidence and
unverified changes interpreted as success. Execute representative quick paths.

T1 local evidence: 130 planner/cache/evidence regression tests pass; the full
Portal check passes (50 routes). A structural comparison against the parent
confirms all 13 full lane entries retain their requirements, commands and notes.
A runtime mutation made both profiles omit Creator: their parity still agreed,
but the independent `[creator, portal]` oracle failed at the intended assertion.
The mutation changed no source or build artifact; the original classifier was
restored by the scoped mock.
Creator quick, one Linux cold execution with dependencies already installed and
Node 26.8.1: build/typecheck 2.001 s, 73 Vitest files / 1,277 tests 78.406 s,
offline tests 0.184 s; total 80.6 s. This is not a full-browser result or a
before/after workday sample. Native cold build took 292.932 s. The complete
205-test fast tier passed on the warm rerun with owned
`TMPDIR=/tmp/lmdj-1996-profiles-tmp`: configure 0.663 s, build 1.101 s,
tests 135.565 s, lane total 138.7 s (n=1 successful warm execution). The first run failed one of 205 fast tests:
`project_io.authoring_history` could not create its sample staging directory
under `/tmp/.lmdj-host`, which was owned by root with mode 0755. A diagnostic
built from the unchanged test and current libraries exposed `Permission denied`;
this is not evidence of a product regression. Preserve that failure and rerun
with an owned `TMPDIR`, without changing the assertion or another user's files.
The operational pitfall is recorded in the additional declared file. Its 15
ledger checks and all 77 staged ownership checks pass.
Precommit main refresh still resolves to `deb95de722b845d708371e90bcac138ae5e25e01`;
no intervening successor changes the premises.

### T2 — Split expensive Web proof and CI-contract work by actual inputs

T2a starts from local T1 commit `e902498d`, with integration main still
`deb95de722b845d708371e90bcac138ae5e25e01`. Both public Web proofs still make two
clean distributions and have no incremental complete-journey entry. Runtime
nonbrowser verification still builds every native target before running just
three named Host tests. These premises remain outstanding at both revisions.

T2a declared files: `scripts/creator-web.sh`, `scripts/web-runtime-host.sh`,
`tests/build/ci_web_proof_server_test.py`,
`tests/build/ci_local_audio_output_test.py`,
`apps/docs-site/docs/operations/testing-and-proof.mdx`, and this plan.
Add explicit `quick` Web entries that build one incremental distribution and
retain all existing browser journeys (including the Creator deployment fixture).
Keep existing `proof` clean-build/reproducibility behavior. Both routes retain
the audio-output wrapper and propagate browser failures. Creator packaging still
requires a committed clean tree. Local UI-only quick and main defaults are not
rewired until the affected-boundary selector and consumers are ready.
Build only the three owning native test targets in Runtime nonbrowser checks.

Lowest-tier checks execute the actual shell proof functions with recorded build
and journey calls, assert each mode against its absolute workload (not just
against the other mode), and prove a failing browser gate fails both entries.
Run wrapper, Web server, threading-preseed, acceleration and Creator package
contracts, shell syntax checks, Portal check and a real Web quick journey.
T2b remains the CI-contract dependency selection and narrow PR-Agent seam work.

T2a local checks: 64 tests across the five declared Web/wrapper/package
contract suites pass; both scripts pass `bash -n`; Portal check passes all
50 routes. The three actual Runtime native seam targets build and their three
CTest cases pass (56.32 s). Precommit main remains `deb95de722b845d708371e90bcac138ae5e25e01`.
The real Creator quick run requires a clean committed tree for packaging, so
this local commit freezes its input before that postcommit acceptance. Its
result belongs in the PR evidence; a source checkpoint is not a journey pass.
No additional qualifying pitfall occurred in T2a.

Primary files: `scripts/creator-web.sh`, `scripts/web-runtime-host.sh`,
`scripts/ci/local_lanes.json`, `.github/workflows/pr-contract.yml`, and their
existing entry-point/contract/browser tests. Declare any new selector and
ownership routing before implementation; inspect producer/consumer dependencies
before narrowing `scripts/ci/` rules.

Web quick uses one incremental build and complete affected journeys. Full
retains both clean builds, reproducibility comparison and every browser leg.
Preserve #1993's frozen-fixture/deployment journey when relevant. CI contracts
may select a module plus consumers; the PR-Agent real-handler seam still runs
for its source/config/lock/fixture boundary and in full requests. Unrelated
module changes should not reinstall it. Do not parallelize Web proofs sharing
the same destructive build root.

Lowest-tier tests: runner selection and command execution, positive controls
for affected/unknown inputs, and a real selected journey. Prove full inventory
retention independently of the new selector. Defects caught: omitted consumer
tests, missing acceptance legs, stale bundles and incorrect proof labels.

T2b implementation worktree starts from `2395f7b3`; refreshed integration main
is `deb95de722b845d708371e90bcac138ae5e25e01`. The PR job still discovers every
CI test and always installs/runs the pinned real-handler seam. The local full
entry has the same behavior; neither includes dependency-focused selection.

T2b declared files: new `scripts/ci/contract_selection.py`, new
`tests/build/ci_contract_selection_test.py`, `scripts/ci/local_lanes.json`,
`scripts/ci/local_preflight.py` (retain optional seam runtime in cache identity),
`.github/workflows/pr-contract.yml`, `tests/build/ci_workflow_topology_test.py`,
`apps/docs-site/docs/operations/testing-and-proof.mdx`, and this plan.
Use a small audited source/consumer group for local preflight tooling, including
its direct local-lane, workflow, shipping-skill, policy-parity, toolchain and
classification-input contracts. New/unmapped CI dependencies keep complete
CI tests and the real-handler seam; full always retains both. Detect newly
referencing consumers and fall back to full instead of trusting a stale group.
Reuse canonical path ownership to disregard changed paths owned exclusively by
other lanes. This changes tests within the CI lane, not lane ownership.
The PR job and explicit local quick profile consume this same selector; existing
main/full execution remains unchanged until T3. Missing Git inputs fail closed.

Verify exact selected test inventories, an unmapped/new-consumer full fallback,
PR-Agent source/config/lock/fixture positive controls, unchanged full discovery,
CLI failure propagation and actual workflow conditions. The selector's own
contract always runs. A low-cost module change must not allocate the unrelated
Python 3.12 seam environment; affected or uncertain changes still do.

T2b verification: the complete selector execution discovered 93 files and
ran 2,650 tests in 227.540 s (72 existing environment-specific skips). The
separate pinned real-handler integration passed: its parent ran 72 tests in
78.897 s with one expected unavailable-in-parent dependency check; the real
handler proxy uses the locked environment. Focused execution of the ten audited
files passed 328 tests in 14.301 s (n=1; this is a workload sample, not a
workday savings claim). Two subsequent real-Git inventory tests cover dirty/
untracked paths and both sides of renames; the final selector suite passes all
11 tests. The final missing-output seam fallback runs unless selection emits
explicit `false`; its 61 topology tests and pinned actionlint pass. All 77
staged ownership tests and the complete Portal check (50 routes) pass.
The final source has these two added inventory tests and the conservative
missing-output condition beyond the initial full-run sample; no full-head or
strict before/after benchmark is claimed from that sample. Existing full lane
commands and main batch execution remain unchanged. No new qualifying pitfall.
Final focused execution includes the two new inventory tests: 330 tests pass
in 14.073 s (n=1). Precommit main is still
`deb95de722b845d708371e90bcac138ae5e25e01`.

### T2c — Repair the updated MASTER boundary in browser verification

The first real T2a quick run on `2395f7b3` retained two failing Chromium tests,
not a passing complete journey. Main remains `deb95de722b845d708371e90bcac138ae5e25e01`.
One failure is a stale test assumption after #2000 (`116280f9`): Perform now has
three 0–1000 FX sliders and a separate 0–100 device MASTER slider. The replay
stop test applies FX neutral 500 to every slider, including MASTER=100.
The new product behavior is already implemented and its component tests pass;
change only this browser assertion, not product code or the slider ranges.

Declared files: `tests/platform/web/creator/creator_web_perform.spec.mjs` and
this plan. Require each of Filter/Delay/Reverb to return to 500 after Stop
Replay, retain the HOLD and Pattern-idle assertions, and separately require
MASTER to preserve its pre-recording value. The existing failed run is the
negative control against a freshly built artifact. Verify the corrected full
replay-stop journey on that unchanged product artifact with a fresh Playwright
process before commit. Version impact: none. Documentation impact: none — the
current product/verification contract is unchanged; this repairs its test.

T2c verification: the complete corrected replay-stop journey passes in a fresh
Chromium process (1 test, 32.6 s) against the unchanged `2395f7b3` product
distribution. The original new-slider failure remains in the T2a log. The
remaining T2a browser groups (Catalog, Sample, WebKit capability, Capture and
deployment) passed; the overall T2a run exited 1 and is not a full quick pass.
No new pitfall qualifies: this assertion boundary is derivable from product code.
Precommit main still resolves to `deb95de722b845d708371e90bcac138ae5e25e01`.

The independent overview timeout remains outstanding. Its viewport/layout
matrix and state/recovery journey need separate tests without dropping any
assertion, viewport, reload leg or widening the existing budgets (T2d).

### T2d — Separate overview layout from state recovery verification

Main refresh remains `deb95de722b845d708371e90bcac138ae5e25e01`; task base is
`c53744b9`. The initial fresh T2a artifact timed out at the final Project reopen
in the overview test. Its 3-viewport × 4-mode layout matrix and four screenshots
share one 30-second test budget with an independent state/failure/recovery journey.

Declared files: `tests/platform/web/creator/creator_web_hardware_layout.spec.mjs`
and this plan. Move the entire unchanged layout matrix into its own test; keep
all loading, failure, unchanged-truth, retry, delete, undo, System identity,
back-navigation and reload/reopen assertions together. Preserve the state test's
768×600 viewport and Perform-to-Sample transition. Both tests keep the default
30-second budget; no journey is divided across browser contexts. Verify both
against the same freshly built product artifact with fresh Chromium contexts.
Version impact: none. Documentation impact: none — only independent test facts
are separated; product behavior and acceptance requirements remain unchanged.

T2d verification: both tests passed in fresh Chromium contexts (2 tests,
41.4 s total); each retained the default 30-second budget. The full recovery
journey reaches the Project-ID assertion after reopening. All original layout
viewports/modes, screenshots and state-transition assertions are retained.
No new process pitfall applies. Precommit main remains
`deb95de722b845d708371e90bcac138ae5e25e01`.

### T2e — Reduce incidental fixture history in the overview state journey

The complete rerun on `3ab53cad` still times out in the state journey under its
normal two-worker group, although the isolated test passed. Trace timestamps
show 11.13 s importing the 750 KiB general fixture with 64 assignment history
entries; the journey only uses B03. Its later mutation/Undo/System/reopen legs
exhaust the unchanged 30-second budget. Preserve this failed rerun; T2d alone
was insufficient. Main remains `deb95de722b845d708371e90bcac138ae5e25e01`.

Declared files: `scripts/creator-web.sh`,
`tests/platform/web/creator/creator_web_hardware_layout.spec.mjs`,
`tests/build/ci_web_proof_server_test.py`, and this plan.
Extend the existing real-Core fixture generator with a closed overview mode
that assigns only B03. Keep normal 64-Pad fixtures and the layout matrix intact.
Only the independent overview state journey imports this smaller fixture;
retain every original action, failure/retry, truth and reload assertion.
Generate via the real Application Facade/packager, with the same reproducibility
check. Verify both fixture inventories and a fresh complete state journey;
then the complete owning browser group on a clean committed source checkpoint.
Version impact: none. Documentation impact: none — fixture setup is smaller;
public verification tiers, product behavior and acceptance legs are unchanged.

T2e evidence: the actual generator/packager produced a 50,769-byte overview
fixture instead of the 767,554-byte general bundle. Regenerated general output
is byte-identical to the prior general fixture. The complete state journey
passes in 15.8 s with its unchanged 30-second budget while the original full
proof continues other browser cases. All 17 Web mode/server/fixture contracts
and 24 audio wrapper cases pass. Complete owning-spec verification follows the
source checkpoint. No new process pitfall; the extra history is ordinary test
data visible in the generator.

### T3 — Switch daily defaults and merge/main consumers together

T3a freezes a shared daily workload policy before wiring its consumers.
Current main is still `deb95de722b845d708371e90bcac138ae5e25e01`; implementation
base is `3ab53cad`. Full lane ownership remains unchanged. Daily execution can
report a selected lane as deferred to complete verification; it never reports
that lane as passed. Unknown paths and foundational/Contract/build changes
retain full fallback. Ordinary audited CI tooling changes run CI contracts;
ordinary Creator UI changes run build/unit/offline plus the complete authoring,
playback and durable-reload browser smoke. Persistence, Runtime, capture and
concurrency boundaries retain their owning journeys or complete checks.

T3a declared files: new `scripts/ci/daily_verification.py`, new
`tests/build/ci_daily_verification_test.py`, `scripts/ci/contract_selection.py`,
`tests/build/ci_contract_selection_test.py`, and this plan. The contract-selector
consumer scan identified the new policy test's preflight-path fixture; retain
that conservative consumer in its audited group and absolute inventory oracle. This commit only
provides the pure shared policy; no default, scheduler or merge obligation
changes until consumers are coordinated. Tests use independent absolute
inventories for representative paths, unknown/deleted inputs, mixed changes,
platform-specific risk, and explicit full requests. Version impact: none.
Documentation impact: none — not yet a public execution path.

T3a verification: 14 independent daily-policy cases and all 11 contract
selector cases pass; all 77 staged ownership checks pass. New/unknown Creator
components retain complete journeys; only the enumerated presentation
components, CSS and unit-test family use smoke. Precommit main is unchanged.

T3b adds Creator smoke using the existing complete deployment journey.
Declared files: `scripts/creator-web.sh`,
`tests/build/ci_web_proof_server_test.py`,
`tests/build/ci_local_audio_output_test.py`,
`apps/docs-site/docs/operations/testing-and-proof.mdx`, and this plan.
Main is unchanged; task base is `5fc95ae9`. Keep the owned ephemeral server,
audio-output wrapper and packaged artifact identity. Smoke makes one incremental
build, runs all Creator UI/unit/offline tests, then the unchanged browser journey
through authoring, playback and durable reload. Complete browser groups and
fixture generators remain in quick/proof. Full retains byte reproducibility.
Verify actual shell mode execution, independent browser inventories and failure
propagation, existing wrapper/package/server contracts, Portal, and the real
smoke entry after its clean-source checkpoint. This is not release evidence.
Documentation impact: required; affected route: /operations/testing-and-proof.

T3b local verification: 15 Web mode/server contracts, 24 audio wrapper cases,
13 build-acceleration cases, 3 thread-preseed cases and 15 Creator package cases
pass. Shell syntax and the complete Portal check (50 routes) pass. The browser
mode harness executes the actual shell function: all eight complete groups
remain, smoke selects only the unchanged durable deployment journey, and its
failure propagates. Real smoke acceptance requires this clean-source checkpoint;
it remains pending until the original complete quick run releases its build root.
No new qualifying pitfall. Integration main is still
`deb95de722b845d708371e90bcac138ae5e25e01`.

T3c first adds the frozen workload/evidence boundary, without enabling it.
Declared files: `scripts/ci/incremental_batch.py`, `scripts/ci/batch_verdict.py`,
`scripts/ci/batch_execution.py`, `scripts/ci/batch_evidence_validation.py`,
`scripts/ci/batch_runtime.py`, `scripts/ci/batch_controller.py`,
`scripts/ci/report_runtime.py`, new `tests/build/ci_daily_evidence_test.py`,
`tests/build/ci_batch_execution_workflow_test.py` (its real-Git fixture must
include the new imported workload validator), and this plan. Base `50f0d600`; main is unchanged. Requests may carry a closed
per-suite workload map only for automatic requests. Historical requests with no
map retain complete behavior. The execution artifact, raw-needs reconstruction,
verdict and reporting all bind to that same map. Deferred jobs cannot execute or
produce observations. Quick success is explicitly `quick-passed`; it cannot
clear full debt, close full failure buckets or authorize candidate verification.
Missing quick evidence retains debt, while intentional deferral is not failure.

Verify complete producer→raw-needs→verdict→journal→report journeys and negative
cases for missing/mismatched maps, forged full passes, deferred execution,
candidate substitution and existing full debt. Run all existing owning CI
contracts. Documentation impact: none — the optional format is not emitted by
automatic admission until the following coordinated consumer/default cutover. New automatic requests bind their workload
map to the frozen request; historical requests retain complete semantics.
Quick/deferred results cannot clear old full verification debt or close full
failure buckets. Explicit candidate/node and bootstrap retain all 15 suites.


T3c verification: all 2,688 CI contracts executed (72 existing environment
skips). Sixteen cases initially failed because the real-Git workflow fixture
omitted the newly imported validator, all in the same workflow suite. After
including that source in the fixture, all 35 workflow cases and all 16 new
daily-evidence cases pass. All other tests passed in the complete run. This
retains the initial failed run; no assertion or scope was relaxed. No new
qualifying pitfall. All 79 release batch-evidence regressions also pass. Defaults and automatic
request construction remain unchanged.

The ordinary merge obligation has an independently reviewable policy
prerequisite: `docs/plans/2026-10-11-lmdj-daily-verification-obligation.md` on
`docs/daily-verification-obligation`, based on current main. That Task verifies
its only selected batch-only lane (Deploy Contract) under the live old rule
before shipping. Once merged, the execution PR follows the new Task-specific
obligation; a draft never waives its own current live checks.

T3d coordinates actual execution defaults and automatic admission.
Base `27622dd2`, integration main still `deb95de722b845d708371e90bcac138ae5e25e01`.
Declared files: `scripts/local-ci.sh`, `scripts/ci/local_preflight.py`,
`scripts/ci/local_lanes.json`, `scripts/ci/daily_verification.py`,
`scripts/ci/batch_controller.py`, `scripts/ci/batch_evidence_validation.py`,
`.github/workflows/ci.yml`, `.github/actions/web-ci-proof/action.yml`,
`tests/build/ci_local_preflight_test.py`, `tests/build/ci_batch_controller_test.py`,
`tests/build/ci_batch_execution_workflow_test.py`,
`tests/build/ci_workflow_topology_test.py`,
`tests/build/ci_build_acceleration_test.py`,
`tests/build/ci_classification_inputs_test.py`,
`docs/quality/core-test-policy.md`,
`apps/docs-site/docs/operations/testing-and-proof.mdx`, and this plan.

Local CLI defaults to quick, retaining explicit full and strict legacy receipt
audits. Deferred lanes remain in ownership output, execute no commands and emit
no pass/cache receipt. Hook full opt-in explicitly chooses full; migrate only
exact generated hooks with separate preserved backups. Automatic admission
freezes daily workloads from the complete interval and historical policy union.
Authenticated review suggestions can add full work; missing historical policy
keeps full fallback. Executable debt uses complete work, paused debt survives
quick success, and explicit candidate/node/bootstrap remain complete.
The existing admitted DAG uses the frozen map for Core fast, CI selector and
Web smoke/journeys; full commands remain. Shared Web action source joins the
frozen control-source compatibility closure. No new controller, trigger, reset,
branch protection change or automatic release.

Tests: real-Git local plans (including dirty/deleted/unknown paths), actual CLI
and hook execution, complete interval/debt/advice admission, actual workflow
prepare/judge and Web action commands, source-compatibility rejection, full
inventory retention and all owning CI regressions. Run pinned actionlint and
Portal. Representative real Core/Creator checks remain bound to their recorded
source revisions; no unmeasured platform or workday savings claim.
Documentation impact: required; /operations/testing-and-proof.

Primary files: `AGENTS.md`, `CLAUDE.md`,
`.agents/skills/issue-done/SKILL.md`, `docs/governance/git-workflow.md`,
`docs/quality/core-test-policy.md`, `.github/pull_request_template.md`,
`scripts/ci/local_preflight.py`, `scripts/ci/batch_evidence_validation.py`,
the scope/self-test policies and their actual consumers,
`.github/workflows/{pr-contract,ci,core-nightly,self-test-report}.yml`,
their existing contract tests, and affected Portal pages. Freeze the complete
consumer list and per-file task subdivision after T1/T2; do not bundle unrelated
controller, recovery or release repairs.

Replace the broad local batch-only obligation with explicit daily plus
change-risk evidence; update checks, templates and instructions in the same
cutover. Daily main batches use that same inventory. Exact candidate/explicit
full requests retain full inventory and release-evidence semantics. Deferred
checks stay unverified; never turn them into successful full results or erase
verification debt. Existing protection, current-head review and conversations
remain required. Do not write `accepted-risk` without an actual owner decision.

Lowest-tier tests: all changed evidence producers/consumers and routing, with
absolute quick/full expected inventories and a negative proof that quick cannot
authorize a complete candidate. Then representative daily runs and one exact
full candidate verification (no publication). Record representative cold/warm
timings; report unmeasured platforms instead of extrapolating a savings ratio.

## Completion criteria

T0 begins optimization; it does not complete #1996. The issue remains open until
T1–T3 and the normal-workday timing/coverage comparison are complete. Every
removed routine invocation has an explicit full or affected-change destination.
No coverage floor, timeout, stress budget or journey assertion is weakened.

## Version Management

Version impact: none — verification orchestration and documentation do not
change Product, Module, Provider or Contract identities or public behavior.

## Documentation impact

Documentation impact: required
Affected portal pages: /operations/testing-and-proof

Update the current page with each shipped behavior, not future defaults.
T3 must enumerate additional affected pages from its final consumer inventory.
Run `scripts/docs-site.sh check` for each Portal-affecting task.

T3d interval inventory correction: also declare `scripts/ci/contract_selection.py`
and `tests/build/ci_contract_selection_test.py`. Batch quick CI must classify
every first-parent delta, including reverted files; endpoint diff is insufficient.
The local working-tree selector keeps its existing dirty/untracked behavior.

T3d fixture/consumer closure: also declare `tests/build/ci_batch_runtime_test.py`
and `tests/build/ci_change_scope_test.py`. The runtime fixture must create and
commit the newly bound action path; every derived report/discovery fixture uses
that same producer. The existing executor-route oracle must name the retained
`creator:full` dispatch after introducing workload modes. The first complete
2,703-test run retained 401 fixture setup errors and two old route expectations;
these are corrected at their owning fixture/assertion, never skipped.

T3d downstream planning consumer: declare `tools/canary/planning.py`,
`tools/canary/planning_journal.py`, and `tests/build/ci_canary_planning_entry_test.py`.
The complete regression exposed a missed consumer outside scripts/ci: its retained
verdict validator must bind the frozen daily map and its closed source-status
codec must retain quick-passed. A successful daily result remains only a planning
wakeup, as a focused full result already was; planning independently recomputes
site/version intervals and test floors and grants no admission or deployment.
Missing daily evidence must preserve intentional deferred outcomes. Keep every
existing planning recovery leg and add an actual daily-source proof of unchanged
null delivery progress and recomputed full site-bootstrap floors. No new trigger,
planner authority or execution gate is introduced.

T3d documentation closure: also declare `AGENTS.md`, its byte-identical
`CLAUDE.md`, and `docs/governance/git-workflow.md` for the actual quick default
and explicit full command. Refreshed main is now
`82c010d0391b956f871d34ecb40720f9a7e0a8d7`: #2012 merged after its complete
Deploy Contract pass (504.3 s), authentic exact-head review run 38103277676
with no findings, clean conversations and live protected expected-head squash.
Its Task-specific merge obligation is live; no feature draft self-waiver applies.
No intervening product or execution change supersedes the remaining work.

Actual committed-source Creator smoke on `27622dd2` passed: all 1,277 UI tests,
offline checks and the complete deployment authoring/playback/durable-reload
journey (16.4 s). The UI unit suite took 80.15 s; both n=1. The corrected whole
hardware spec passed 7/7. The second pre-fixture complete quick run on `3ab53cad`
retains its Overview timeout; a fresh complete quick on `27622dd2` is in progress.

The final fixture repair preserves actual daily mode in generated verdicts and
marks genuinely deferred jobs skipped. Runtime 81, Canary planning/recovery 119,
and report progress 8 tests pass; this includes the previously failing consumer.
An in-memory shared-omission mutation removed the Web action from both executor
and validator lists: they still agreed, while the independent action-path oracle
failed. A fresh normal oracle run passed; no source/test artifact was replaced.
All thirteen full lane entries compare structurally identical to the prior head.

Final T3d complete CI-control regression: **2,705 tests, 251.093 s, PASS**
(72 pre-existing environment skips; the separately run pinned real-handler seam
remains its own evidence). Complete Portal: 50 routes/internal links PASS.
Release batch-evidence boundary: 79/79 PASS. Pinned actionlint PASS. CLI default
and real body-declaration checks PASS; this broad workflow-changing Task correctly
falls back to full work despite the quick default. Final message-only fixes name
`--profile full --lanes` in full-receipt remedies; local regression rerun follows.
The JSON table's unaffected entries keep their prior formatting; resolved data
and all full commands remain identical.

### T3e — Bind compiler delegates in the local execution cache

Review of `29f1f7a5` identified a real boundary behind its speculative wrapper
comment: replacing the compiler behind `CC="ccache gcc"` with the same advertised
version need not change the wrapper stat/version identity. Likewise an existing
CMake configuration can keep a compiler different from the current CC default.
Declare `scripts/ci/local_preflight.py`, `tests/build/ci_local_preflight_test.py`
and this plan. Bind resolved executable arguments and the configured compiler
commands in existing owned CMake caches. This changes only advisory execution
cache identity; complete source-bound receipts stay unchanged. Cover same-version
delegate replacement and configured-compiler replacement with a red-before-fix
regression, then the complete local preflight suite. Documentation impact: none;
the documented compiler-aware cache contract is being repaired, not changed.
Version impact: none. Main remains `82c010d0391b956f871d34ecb40720f9a7e0a8d7`;
this work is not already delivered there. No qualifying new pitfall: the owning
regressions express this cache defect.

T3e verification: both delegate/configured-compiler replacement regressions failed
at their cache-identity assertions on the old source, then passed with the fix.
The complete local preflight suite passes 136/136 and selector contracts 12/12.
No product artifact or source was restored with a preserved timestamp. Seven
other automated observations were dispositioned with owning-code/real-Git evidence:
flat selector inventory, both rename paths, intentional control-plane workloads,
explicit deferred/quick evidence, retained full debt, fresh atomic Web packaging,
and conservative missing seam output. The compiler finding remains unresolved
for the new-head automatic repair recheck, not manually cleared.

### T3f — Bind the checked-out Web action for daily workloads

Final source-binding inspection found that local composite actions are loaded
from the target checkout, while reusable workflows come from executor control.
When main advances after a controller starts, comparing only the two control
revisions does not bind the actual daily Web dispatch. Declare
`.github/workflows/ci.yml`, `scripts/ci/batch_runtime.py`,
`tests/build/ci_batch_execution_workflow_test.py`,
`tests/build/ci_batch_runtime_test.py` and this plan. For a frozen quick/journey
Web mode, require the target Web action to match frozen control before heavy
outputs and when authenticating a result. Complete/legacy requests retain their
existing target-owned full scripts. Test the changed target with unchanged
controls, retain full compatibility, then run both owning suites. Documentation
impact: none; this repairs the already documented exact-source evidence boundary.
Version impact: none. Main still `82c010d0`; no new trigger or gate is introduced.

T3f verification: the actual inline preparation script admitted the mismatched
target action before the fix (the named real-Git regression failed at its
nonzero-exit assertion); after repair, all 40 workflow execution tests and 82
runtime tests pass. Candidate/legacy full compatibility remains covered.
Pinned actionlint passes. No product test selection, timeout or retry changed.

Final complete Creator quick on committed source `27622dd2` exited 0:
1,277 UI tests and offline checks, main Chromium 91 passed/1 conditional skip,
Catalog 4 passed, Sample 10 passed/1 skip, WebKit 1 passed, capture 8 passed/1
skip, denied-permission 1 passed/8 inapplicable skips, Sample WebKit 1 passed,
and the durable deployment journey 1 passed. The log window is 1,830 s, versus
140 s for the previously recorded smoke on the same committed source and warm
worktree (n=1 each; not a normalized workday savings estimate). Two-build byte
reproducibility is not part of quick and is not claimed. The older failed runs
remain retained. Independent review of `a8958e15` produced no new findings;
T3f requires review on its own final head.

Shipping refresh: main advanced to `98f8ba113e7cb4c619ad0d34b69d66ea29058f1c`
via #2013. Its two Creator native-monitor observation documents change no
verification producer, consumer, policy or tested source; no premise or test
result above is superseded. The current-head compiler repair model review is
clean, but its separate repair adapter refused the old finding's inconsistent
source quote/anchor. Preserve that refusal; it is not an automatic resolution.

### T3g — Bind tool contents when installation metadata is preserved

Review run 38106116405 of `0ecd9889` identifies a further cache boundary:
an installation can change executable bytes while preserving its size, mtime
and advertised version. Declare `scripts/ci/local_preflight.py`,
`tests/build/ci_local_preflight_test.py` and this plan. Include a streaming
executable content digest in tool identity and version-probe memoization.
Memoize file reads only within this process using resolved path, inode, size,
mtime and ctime so multiple selected lanes do not repeatedly read large tools.
First prove the same-size, restored-mtime, fixed-version replacement collides
on the old implementation; then run the complete local preflight and selector
contracts. Main remains `98f8ba113e7cb4c619ad0d34b69d66ea29058f1c`, which
does not contain this cache implementation. Documentation impact: none; this
repairs the existing input-bound cache promise. Version impact: none. No new
product check, timeout or full-lane obligation is introduced.

T3g verification: the preserved-size/mtime/version replacement failed the
identity inequality on the old implementation; after repair the complete local
preflight suite passes 137/137 (10.421 s), and selector contracts pass 12/12.
No qualifying pitfall: the owning regression fully expresses this cache defect.
