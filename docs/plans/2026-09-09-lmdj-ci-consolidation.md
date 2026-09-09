# CI consolidation program

Status: approved for execution on 2026-09-09; coordinator-led, one Task per
Pull Request. No release, deployment, journal reset or readiness switch is part
of this program.

## Supersession and decisions — 2026-09-10

The owner-approved [CI reliability, recovery and execution cost plan](2026-09-10-lmdj-ci-reliability-and-cost.md)
is authoritative for current scope, task order, acceptance and authorization.
Codex has taken over coordination of the same Orca Run and umbrella #1089.
The observations, original exit criteria and phase ledger below are historical;
they are not fresh verification or instructions to execute superseded choices.

D1–D4 are decided in the table below. In particular, a label alone never
waives independent exact-head review; only the owner can approve an exception
with an exact SHA and reason. Quota recovery respects the existing operation
budget and leaves debt for a later tick. New managed buckets require causal,
authenticated same-suite recovery; historical buckets need individual review,
not bulk closure. Checkpoint work is design-only, host inventory is read-only,
and stress work measures a cause rather than changing concurrency or tolerance.
P1.4 still awaits the next independently authorized genuine publication; this
program does not initiate one. Historical green or not-selected results cannot
satisfy that acceptance.

## Why

A six-slice read-only review on 2026-09-09 (routing, incremental controller,
PR review, canary, runners, deploy/release) found a CI system whose safety
properties hold but whose signal has degraded:

| Measured on 2026-09-09 | Value |
| --- | --- |
| Red gates on `main` | 3 classes: `ci_pitfall_ledger_test` (#1078), canary suites (#1088), Node parity (#1056) |
| `publish-release.yml` recent runs | 8/8 failed while every Release succeeded |
| PR review attempts that published a review | 2 of 15 (9 all-backend `runtime_failure`, 4 lost to a merge within 3 minutes) |
| Merged PRs with a bot review | 12 of 40 |
| Open `self-test` Issues / ever closed | 32 / 0 |
| Dead code kept in live workflows | `pre-heavy-gate`, `merge-queue.yml` (199), `pr_gate.py` (435), `phase_gate.py` (264) |
| Documentation-impact gate | condition can no longer be true; only `local-ci.sh --pr-body` checks it |
| Actions runs per day | ~1,380; about half cancelled or skipped |
| Canary planning wakeups executed | 0 of 129 at review time, 0 of 175 at plan commit (all skipped); `workflow_dispatch` never run |
| CI infrastructure + its tests vs product source | 54.6k vs 113.6k lines |

The governing defect is not any single item. It is that a red gate no longer
reliably means "something is wrong", and a green merge no longer reliably means
"someone looked". Every Task below restores one of those two meanings or removes
code that cannot contribute to either.

## Goal and exit criteria

The program is complete when all of the following hold on `main` and are
demonstrated by a fresh main batch or a linked run, not by local claims:

1. `python3 -m unittest discover -s tests/build -p 'ci_*_test.py'` passes with
   the pinned actionlint, and `scripts/creator-web.sh test` passes under the
   toolchain Node. Zero known red gates on `main`.
2. `publish-release.yml` is green on the next real publication, or its
   post-publish audit step is removed with the defect it caught moved to a gate
   that can be green.
3. Every retired mechanism named in Phase 2 is deleted, and no test asserts a
   condition that cannot occur.
4. A self-test bucket Issue closes automatically when the same suite is green in
   a later batch, and one infrastructure event files one Issue, not one per
   suite. Storage Issues carry `ci:storage` and are excluded from work queries.
5. A PR either carries a published current-head review or an explicit
   `review:skipped` label with a reason before squash merge; `issue-done`
   enforces the wait. A placeholder payload cannot be published as `reviewed`.
6. A primary REST quota exhaustion is classified as `unknown`, retried until
   the reset window, and never reported as "controller not live".
7. Owner decisions D1 to D4 are recorded here with their outcome.

## Rules for every worker

These restate repository governance; the coordinator rejects a `worker_done`
that violates any of them.

- Read `AGENTS.md`, `docs/governance/git-workflow.md`,
  `docs/governance/minimization-principle.md` and
  `.agents/skills/issue-done/SKILL.md` first. Search `.agents/pitfalls/` by the
  Task's `area:*` labels before designing.
- One Task is one Conventional Commit of its declared files on a `fix/*`,
  `docs/*` or `feat/*` branch in an isolated worktree created from
  `origin/main`. Do not touch `main`. Do not edit files outside the declaration;
  if the declaration is wrong, `ask` the coordinator before widening.
- Never lower a coverage floor, widen a timeout, skip a test, de-select a lane
  or drop a journey leg to get green. Reduce a defect before fixing it: the
  regression test must fail before the fix and pass after.
- A deleted mechanism takes its tests, policy rules and documentation with it in
  the same commit. A kept mechanism keeps its tests unchanged.
- Ship through `issue-done`: Task-specific tests, staged file inspection,
  `git diff --cached --check`, push, PR with all governance declarations,
  current-head review evidence, squash merge. Report the merged SHA.
- `worker_done` must carry: merged SHA or blocker, the exact commands run with
  their pass/fail counts, files modified, and anything left undone. Failure is
  reported with `--outcome failed`, never only in prose.
- Do not close, relabel or comment on GitHub Issues other than the one the Task
  names; the coordinator owns Issue hygiene.

## Owner decision gates

The original alternatives were considered on 2026-09-09; the owner confirmed
these outcomes on 2026-09-10. No decision in this table remains pending.

| Gate | Approved outcome | Correction to the original proposal |
| --- | --- | --- |
| D1 | Change-selected advisory CI contracts, static docs and documentation-impact checks on trusted self-hosted capacity; no new required check. | `ci_contract` and `docs_static` do not run Creator parity. The original “all three red-gate classes” and “a few minutes” claims were unsupported; measure cost and retain complete selected contracts. |
| D2 | Freeze automatic Canary Planning `workflow_run`; retain manual entry. | The proposed later manual `init` is not authorized; no init/readiness activation in this program. |
| D3 | Independent current-head review; only owner may waive with exact SHA and reason. | `review:skipped` is display only, never authority; author self-review is not independent evidence. |
| D4 | Explicit common Catalog character admission in Worker and proof server, verified on Node 22 and 26. | Existing proof-server grammar/corpus is the semantic baseline; preserve Worker HTTPS and the proof server's explicit loopback HTTP exception. Source/tests only, no deployment. |

## Historical phases and Tasks (superseded by T0–T12)

Model and effort are suggestions for the coordinator when starting a Codex
worker; the coordinator may change them per attempt.

### Phase 1: clear red gates on `main`

P1.1, P1.2 and P1.4 are independent and run in parallel. P1.3 waits for D4.

| Task | Issue | Declared files | Lowest-tier verification | Effort |
| --- | --- | --- | --- | --- |
| P1.1 pitfall area label | #1078 | `.agents/pitfalls/snapshot-page-pin-only-fires-at-freeze.md` | `python3 tests/build/ci_pitfall_ledger_test.py` | low |
| P1.2 canary fixture inventory | #1088 | `tools/canary/metadata_proposal.py`, `tests/build/ci_canary_metadata_proposal_test.py`; `tests/build/ci_canary_assessment_handoff_test.py` only if the coordinator confirms it shares the inventory | `python3 -m unittest discover -s tests/build -p 'ci_canary*_test.py'` | medium |
| P1.3 Node parity | #1056, D4 | per D4: (c) `apps/web-runtime-host/deploy/cloudflare_worker.mjs`, `apps/creator-web/test/server_test.py` and the proof server's matching rule; the fix must not fork behavior by Node version. The Worker change lands in source only; no deployment is part of this program, and parity is proven by the existing two-leg harness passing under both Node versions plus the Worker unit tests | `scripts/creator-web.sh test` under the toolchain Node and the system Node | medium |
| P1.4 post-publish audit | pitfall `post-publish-audit-releasable-ledger` | `.github/workflows/publish-release.yml`, `tools/release/cli.py`, one new or extended module under `tools/release/` for the published-Release verification, the matching `tests/build/release_*_test.py`, the pitfall entry, `.agents/skills/lmdj-release/SKILL.md` | `python3 -m unittest discover -s tests/build -p 'release_*_test.py'`; no live publication | high |

Acceptance: the next main batch after all four merge reports `ci_contract`
green; P1.4 is accepted on evidence from the next real publication.

### Phase 2: delete dead mechanisms and align documents

Depends on nothing; P2.2 and P2.3 touch `ci.yml` and must be sequential.

| Task | Declared files | Verification | Effort |
| --- | --- | --- | --- |
| P2.1 retire queue and gate scripts | `.github/workflows/merge-queue.yml`, `scripts/ci/merge_queue.py`, `scripts/ci/merge_queue_watchdog.py`, `scripts/ci/pr_gate.py`, `scripts/ci/phase_gate.py`, their `tests/build/ci_*_test.py`, `scripts/ci/scope_policy.json` rule for `merge-queue.yml`, `docs/governance/git-workflow.md` "until T6" wording | `python3 -m unittest discover -s tests/build -p 'ci_*_test.py'`; `python3 scripts/ci/change_scope.py` self-check; `scripts/local-ci.sh --list` | medium |
| P2.2 remove `pre-heavy-gate` and dead `pull_request` branches | `.github/workflows/ci.yml`, `tests/build/ci_workflow_topology_test.py` | topology and hosted-runner-policy tests; actionlint with the pinned binary | medium |
| P2.3 documentation-impact gate | depends on D1. If D1 is yes: new `.github/workflows/pr-contract.yml` plus `hosted_runner_policy.json` entry and topology test; the doc-impact check moves there. If D1 is no: delete `check_documentation_impact` input plumbing from `ci.yml` and `architecture-portal.yml`, and change `AGENTS.md`/`CLAUDE.md`/`issue-done` to say the declaration is checked locally only | topology tests; `scripts/local-ci.sh --pr-body` still works | medium |
| P2.4 stale prose | `scripts/ci/change_scope.py` header comments, `docs/governance/git-workflow.md` run-specific history, `docs/quality/core-test-policy.md` lane/suite vocabulary note | `python3 tests/build/ci_change_scope_test.py`; `scripts/docs-site.sh check` if portal pages change | low |

Acceptance: `git grep -n "pre-heavy-gate\|merge_queue\|pr_gate\|phase_gate" -- .github scripts tests AGENTS.md CLAUDE.md docs/governance apps/docs-site/docs`
returns nothing. Immutable Portal snapshots under `apps/*/versioned_docs` and
`versioned_provenance`, pitfall ledger entries, `docs/design` and `docs/plans`
are history and are never edited to satisfy this grep.

### Phase 3: self-test Issue lifecycle

| Task | Issue | Declared files | Verification | Effort |
| --- | --- | --- | --- | --- |
| P3.1 auto-close on green | new | `scripts/ci/self_test_report.py`, `scripts/ci/report_runtime.py`, `tests/build/ci_self_test_report_test.py`, `tests/build/ci_report_runtime_test.py` | red-first test: a bucket with an open Issue and a later green result for the same suite closes with a comment naming the batch; a green unrelated suite does not | high |
| P3.2 one infrastructure event, one Issue | new | `scripts/ci/batch_verdict.py`, `scripts/ci/report_runtime.py`, `tests/build/ci_batch_verdict_test.py`, `tests/build/ci_report_runtime_test.py` | red-first test: a skipped candidate run yields one `missing` Issue listing suites, not sixteen | medium |
| P3.3 storage Issue labeling | manual + `.agents/skills/issue-list/SKILL.md` | coordinator labels #807 #817 #849 #824 #825 #826 #840 #857 `ci:storage` (no pinning; GitHub allows three pinned Issues) and the skill excludes the label | skill text review | low |
| P3.4 bulk close | manual | after P3.1 merges, coordinator closes the sixteen `missing` Issues #874–#879, #881–#890 and fixed buckets with the batch SHA that proves green | none | low |

### Phase 4: review evidence

| Task | Issue | Declared files | Verification | Effort |
| --- | --- | --- | --- | --- |
| P4.1 placeholder rejection | #1062 | `scripts/ci/review_scope.py`, `tests/build/ci_review_scope_test.py` | red-first: the exact Kimi stub payload is refused as `not-reviewed`; a real review still validates | medium |
| P4.2 wait-for-review before merge | #939, D3 | `.agents/skills/issue-done/SKILL.md`; if a helper is needed, `scripts/ci/review_wait.py` and `tests/build/ci_review_wait_test.py` | skill dry-run on a real open PR; helper exits non-zero while the current-head run is in progress | medium |
| P4.3 backend timeout diagnosis | #939 | investigation report as a plan document; code only if the cause is in-repo | reproduce the 5-minute cap against one provider with the pinned action; report | high |
| P4.4 retire unsigned inline clean reviews | #714 | `.github/scripts/retire_clean_review_threads.py`, its test under `tests/build/` | red-first | low |

### Phase 5: controller robustness

| Task | Issue | Declared files | Verification | Effort |
| --- | --- | --- | --- | --- |
| P5.1 quota exhaustion is unknown, not dead | #979 | `scripts/ci/self_test_report.py` (`UrllibGitHubApi` HTTP runtime), `scripts/ci/batch_runtime.py`, `scripts/ci/incremental_completion.py`, `scripts/ci/batch_github_journal.py`, their matching HTTP/runtime tests (corrected 2026-09-10: the original `github_queue_api.py` named the retired queue adapter) | red-first: a 403 with `x-ratelimit-remaining: 0` yields a retry until `x-ratelimit-reset` and an `unknown` classification, never `not live` | high |
| P5.2 journal checkpoint cursor | #979 root | design first as a plan document; implement only after coordinator acceptance | measured GET count per transaction before and after | high |
| P5.3 report-only cron acceptance | #1048 | none unless the acceptance fails | coordinator reads three consecutive report-only runs | low |

### Phase 6: runner single points

| Task | Issue | Declared files | Verification | Effort |
| --- | --- | --- | --- | --- |
| P6.1 host configuration parity check | pitfall `sanitizer-runtime-silent-start-failure` | `.github/workflows/ci-host-inventory.yml`, `scripts/ci/host/`, `tests/build/ci_host_inventory_workflow_test.py` | inventory run fails when `vm.mmap_rnd_bits` or the elastic controller config differs from the repository pin | medium |
| P6.2 control jobs on either general host | `docs/quality/core-test-policy.md` recovery-gap paragraph (about line 288-295) | `.github/workflows/ci.yml`, `self-test-report.yml`, `hosted_runner_policy.json`, topology tests | the first job of each workflow schedules when `contabo` is offline | medium |
| P6.3 load-sensitive stress | #666 | `.github/workflows/core-nightly.yml` concurrency group for the stress lane and `tests/build/ci_nightly_workflow_test.py`; never the overrun threshold | three consecutive nightly stress runs green while a web lane executes | medium |

### Phase 7: canary decision

Depends on D2. If frozen: one Task removes the `workflow_run` trigger from
`canary-planning.yml` and records the freeze in
`docs/plans/2026-09-09-lmdj-result-driven-delivery.md`. If activated: the
coordinator runs one manual `init` and files what breaks.

## Explicitly out of scope

Cloudflare migration Tasks (#873, #921–#927, #867, #985), Stage 11/12 product
work, physical acceptance Tasks, and any release, deployment, Channel promotion,
journal reset or readiness switch. Adding hosted-runner spend is out of scope.

## Coordination

Historical coordinator: the Claude session bound to Orca Run `run_71c2492cd783`. Workers
are Codex agents started with `orca orchestration worker-start`, one per Task,
each in a fresh top-level worktree from `origin/main`. The coordinator accepts a
Task only after re-running its lowest-tier verification in the worker's
worktree and reading the merged PR. Tracking Issue: #1089.

## Version Management

Version impact: none

Reason: this program changes CI tooling, workflows, tests and governance
documents only. No Product Build, Core Module, Provider or Contract identity is
allocated or changed by any Task; a Task that discovers a version impact stops
and reports it.

## Documentation Impact

Documentation impact: none

Reason: this document is a plan under `docs/plans/`. Individual Tasks that
change portal pages (P2.4 if `core-test-policy` is projected; P2.3 if a new
workflow appears in the operations pages) declare their own impact.

Pitfall impact: none for this document. Phase 1 Tasks bump or record the
pitfalls they resolve through `issue-done`.
