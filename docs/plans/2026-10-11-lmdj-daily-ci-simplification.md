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

### T3 — Switch daily defaults and merge/main consumers together

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
