# T5 atomic incremental trigger cutover — ready for authorized cutover

Design: [incremental batches](../design/2026-09-08-lmdj-ci-incremental-batches.md).

The root has verified the O1 gate evidence referenced in the final section.
This local Task is ready for authorized cutover, not already activated; O2
automatic platform-chain recovery remains pending. The root owns final fresh
legacy/protection checks and shipping. Companion present-tense instructions
become operative only after actual cutover. All HOLD statements and incomplete
observations below are historical records of their named preparation stages,
not the current readiness state. No current-main all-green gate is introduced.

## Version Management

Version impact: none — CI control wiring allocates no product or component version.

## Documentation impact

Documentation impact: required

Affected portal pages: /operations/testing-and-proof, /operations/version-and-release

The root agent owns companion documentation in this same isolated worktree;
the workflow agent must not overwrite it. They form one eventual atomic Task.

## Declared files

- `.github/workflows/ci.yml`
- `.github/workflows/self-test-report.yml`
- `scripts/ci/self_test_report.py`
- `scripts/ci/hosted_runner_policy.json`
- `scripts/ci/incremental_entry.py`
- `tests/build/ci_incremental_entry_test.py`
- `tests/build/ci_batch_execution_workflow_test.py`
- `tests/build/ci_batch_runtime_workflow_test.py`
- `tests/build/ci_change_scope_test.py` (retired direct lanes input only)
- `tests/build/ci_grok_review_workflow_test.py`
- `tests/build/ci_merge_queue_workflow_test.py`
- `tests/build/ci_o1_claim_probe_workflow_test.py`
- `tests/build/ci_o1_probe_workflow_test.py`
- `tests/build/ci_review_discovery_workflow_test.py`
- `tests/build/ci_runner_fallback_test.py` (retired hosted job inventory only)
- `tests/build/ci_self_test_report_test.py`
- `tests/build/ci_self_test_report_workflow_test.py`
- `tests/build/ci_self_test_workflow_test.py`
- `tests/build/ci_workflow_topology_test.py`
- `tests/build/ci_incremental_cutover_workflow_test.py`
- This plan.

Root-owned companion files: `AGENTS.md`, `CLAUDE.md`,
`.github/workflows/core-nightly.yml` (two explanatory comments only),
`.agents/skills/issue-done/SKILL.md`, `.agents/skills/issue-list/SKILL.md`,
`.agents/skills/lmdj-release/SKILL.md`, `docs/governance/git-workflow.md`,
`docs/governance/github-work-management.md`,
`docs/governance/version-management.md`, `docs/quality/core-test-policy.md`,
`apps/architecture-portal/docs/operations/testing-and-proof.mdx`,
`apps/architecture-portal/docs/operations/version-and-release.mdx`,
`apps/architecture-portal/test/content-inventory.test.mjs`.
Any release-pipeline specification pointer change needs its exact path recorded
by the root before editing.

## Implementation boundary

Use the existing Self-test Report workflow identity and short controller job lock.
Main push, authenticated completed Self-test Report/Core CI/PR Review callbacks
and an independent 15-minute health tick feed the existing durable controller.
Do not filter PR Review callbacks by main branch: their producer head is a PR.
No daily product-test obligation, new dispatcher, permissions or service follows.

Core CI becomes reusable-only. Preserve all sixteen suites, actual per-suite
selection, fixed product target, trusted current scripts over historical policy,
sanitizer/stress/coverage budgets and native resource locks. Remove the retired
direct manual/daily producer, not historical evidence readers.

Manual exact full is `reconcile` with closed `batch_request` containing stable
`id`, `kind` (`node` or `candidate`) and exact main-history `target`. Omitted
`journal_config` uses authenticated committed fixed production storage; explicit
isolated configuration remains available for recovery. Init never implicitly
initializes production storage. Full selection is enforced by the existing runtime.

Legacy exact reporting uses `report-legacy` with `review_run_id` and
`review_attempt`, through ReportRuntime and Outbox. The old run_id/reconcile
inputs are rejected rather than invoking direct business writes. Published
history readers and original references remain intact. At cutover, inventory
pre-cutover legacy attempts and explicitly report or retain each unresolved source;
new manual full requests are journaled and need no second discovery protocol.

## Fairness and failure boundaries

Persist control output first. An execute action skips automatic report/discovery
steps and releases the controller lock for the product DAG. Other automatic
rounds independently attempt reporting (limit 1) and discovery (limit 1), retaining
durable backlog. Both errors remain visible; one does not skip the other.
They use the same authenticated controller job identity, not an untrusted new job.
Discovery scans run on nonexecuting push/health rounds and PR Review callbacks,
not on idle Self-test/Core CI completion chains; health still repairs missed
review callbacks. Other completion rounds retain independent report/drain.

A count bound is not a wall-clock guarantee: complete authenticated pagination,
artifact loading and a single source can still take minutes. Existing controller
timeout remains unchanged; interruption must retain durable recovery state.
No-new-work health/idle callbacks do not admit product work. GitHub callback chain
depth and scheduled-event delay mean immediate unlimited chaining is not promised.
Actual chain-limit → independent tick → recovery and no-change/no-heavy are O2
acceptance legs, not established by local workflow tests.

### Read-only callback source witness

After both current-run authentication and event/source exact-attempt API
validation, `Entry.control` prints one closed JSON diagnostic line to the
existing job log: schema `lmdj.ci-source-witness.v1`, current
`{run_id, attempt, control, event}`, `source_family`, and source run
`{id, attempt}` or null for push/schedule roots. Authentication failure prints
no witness. This is not the raw event, an execution output, an admission receipt,
a result-schema extension, a report payload or a new artifact. No permission,
queue, journal, authentication rule or product selection changes.

The witness lets an O2 audit link an actual callback (including idle callbacks)
to its API-verified parent without mistaking reusable `referenced_workflows`
for trigger ancestry. It does not assert a chain depth or prove an absent
callback was suppressed by the platform. Actual logs must still be paired with
exact-run API responses, durable state, complete run inventory and the
independent schedule recovery. No O2 remote acceptance follows from this local
diagnostic. Root-authorized T5 activation remains a separate boundary.

The witness's three new actual-Entry fixture regressions first reproduced
missing output (two failing root subcases and a callback parse error), then
passed after the bounded log addition. The full 24-test Entry suite passed;
coverage includes push/schedule roots, actual terminal and idle callback parent
identity, unchanged closed controller result, and zero witness on rejected
current/event/source authentication. These use real local Runtime/Journal
composition with injected HTTP fixtures, not actual GitHub callback acceptance.
The refreshed complete CI inventory and 66 ownership tests also passed; logs
are `/tmp/lmdj-source-witness-all-ci.log` and
`/tmp/lmdj-source-witness-ownership.log`. The witness changes no Portal source;
the separately recorded Portal verification is not a platform-chain test.

## Verification and acceptance

Required local checks: actual inline-command tests, entry/runtime bound tests,
workflow contracts, historical reporter tests, complete CI Python test inventory,
hosted-job inventory, actionlint, staged ownership and nonempty docs-static range.
Portal checks and any unavailable dependencies must be recorded honestly by the
root. No coverage/test removal may be disguised as adapting retired entry tests.

Remote O1 candidate/full-consumer and finite legacy migration evidence are gates
for authorization, not fabricated by this draft. Real cancellation evidence must
retain the recorded expiry race limitation. No new remote exercise occurs here.

## Retired-test migration map

The old ResolverShellTest executed the now-removed direct resolver and legacy
producer shell. Its historical policy semantics remain in `ci_self_test_test.py`
and retained history-reader tests. Current actual malformed input/ref/attempt,
fixed target, historical policy and full/focused needs reconstruction journeys
are in `ci_batch_execution_workflow_test.py`; new default fixed-storage dispatch
and persistence-before-output journeys are in `ci_incremental_cutover_workflow_test.py`.
No dead shell fixture is copied into the repository to imitate a live producer.

Old reporter CLI tests now assert refusal before any API/reconciliation call.
Unknown POST outcome recovery remains covered through the real Outbox and
ReportRuntime tests; the manual legacy workflow uses that consumer, not the
retired direct writer. Product job checkout, actual-head verification, complete
suite inventory, fixed resource roles/timeouts and sanitizer/stress workloads
retain their original assertions. PR Gate/legacy verdict inventory assertions
now name the actual scoped producer; no fake compatibility producer is added.

## Local results (draft)

- New actual inline cutover bridge: 9 tests passed, including evaluation of the
  actual discovery condition across idle self-completions, PR callbacks, push,
  health, execute and failed-control cases.
- Initial full CI run exposed retired-entry assertions plus an import-order
  exception-class split caused by the new test. The new test now loads the
  existing canonical reporter fixture before composing the entry, matching the
  established entry test convention; no Outbox or probe implementation changed.
- Actionlint 1.7.12: both edited workflows passed with only the existing exact
  `unexpected key "queue" for "concurrency" section` compatibility exclusion.
- Root companion content inventory: 4 tests passed. Initial full Portal check
  had 53 passed / 4 failed (three unavailable dependencies and one old daily
  assertion). Root then verified the complete Portal check successfully:
  65 tests, 37 pages, 10 source diagrams / 20 outputs, source facts, release-docs,
  typecheck, 42-route build and internal links. After simplifying the historical
  reporter instructions, the current draft was checked again: session 89072
  exited 0, log `/tmp/lmdj-cutover-portal-full3.log`, including all 42 routes and
  valid internal links. This supersedes the earlier full2 check for those edits.
- Full CI inventory: 1636 tests passed without skips; the additional actual
  manual legacy CLI → outbox → duplicate retry test passed in the 20-test
  runtime-workflow suite. Final combined rerun is recorded below when complete.
- Root independently parsed both workflow versions: only `pr-gate` and old
  `self-test-verdict` jobs removed, only `change-scope` changed. All other 22 jobs
  structurally equal, including both stress callers, scoped verdict, permissions,
  target checkout, timeouts and resource locks.
- Actual staged ownership: 66 tests passed, including the two newly tracked
  plan/test paths. Final docs-static remains pending while the draft is held.
- Reusable caller identity is now the exact built-in GitHub workflow reference
  of the existing main controller, not any non-native workflow. The actual shell
  regression supplies otherwise valid current executor JSON from a foreign
  workflow and verifies refusal before output; 24 execution-workflow tests pass.
- Final combined CI: 1639 tests passed with no skips, log
  `/tmp/lmdj-cutover-all-ci5.log`; actual command used the existing actionlint
  1.7.12 binary on PATH. Both edited execution/controller workflows and the
  root's comment-only core-nightly change pass actionlint with the same single
  queue-syntax exclusion. `git diff HEAD --check` checks the nonempty complete
  staged/unstaged draft; final committed-range docs-static awaits authorization.

## Finite legacy migration audit — not cutover acceptance

Before the root's local preparation commit, the complete staged draft was
rechecked: 1,639 CI tests passed in 38.720 seconds (`/tmp/lmdj-cutover-all-ci6.log`),
66 staged ownership tests passed, and all three edited workflows passed the
same pinned actionlint check. Whitespace checks passed; no unstaged file
changes were left outside the declared Task. This adds no remote acceptance.

The independent read-only audit froze a cutoff of `2026-09-08T00:25:37Z`.
Saved evidence is outside the worktree at
`/tmp/lmdj-legacy-migration-audit.wVesVj`: complete run inventory, exact-attempt
responses, historical plans, all-state Issue inventory, Issue comment inventories
and outbox snapshot. The workflow agent independently rechecked the saved
run/attempt inventory, plans and three Issue observation markers:
38 runs and 41 exact run/attempt responses were all completed, with no legacy
in-flight executor in this bounded inventory. All 41 requested run/attempt
identities matched their actual responses.

The audit found two applicable trusted-main sources and three failure
observations, all already delivered with exact observation markers:

- `34141514828/1/core_tsan_stress/e060be31ed77`: Issue #782 comment inventory.
- `34141514828/1/deploy_contract/9a047f03f70a`: Issue #786 body.
- `34133234184/1/core_tsan_stress/e060be31ed77`: Issue #782 body.

The independent audit reported no undelivered or retention-lost source within
that cutoff. This is a finite historical disposition, not evidence that future
legacy dispatches or manual reruns cannot occur. Refresh the inventory immediately
before an authorized trigger switch, retain any new or uncertain source, and
wait for any newly observed legacy executor; do not erase history or silently
broaden this snapshot's claim. O1, T5 authorization and O2 automatic recovery
acceptance remain separate and are not declared complete by this audit.

Local preparation may be committed after its checks; it is not O1 acceptance.
No push, remote mutation or automatic activation has occurred in this draft Task.

## Integration after PR #872 — still local preparation

Rebased the local Task onto `bc23b4882276c54a8e30c6f1c2e8001fc4a00eb8`.
The integrated tree retains PR #869's standing-authorization precedence,
PR #870's Codex path ownership and committed-new-file check, PR #871's TSan
attempt logging, and PR #872's candidate-only policy preflight and settlement.
No whole-file replacement discarded those changes. The explicit no-release
goal and this Task's activation HOLD remain unchanged.

At local revision `7de8cc30e67655051b36a8f9cb3b472aa65ed5a4`:

- Complete CI Python inventory: 1,665 passed, no skips, 39.638 seconds;
  `/tmp/lmdj-cutover-post872-ci.log`.
- Ownership suite: 66 passed. Final committed-range docs-static passed;
  `/tmp/lmdj-cutover-post872-docs.log`.
- Repository-wide actionlint 1.7.12 explicitly used ShellCheck 0.9.0 and passed
  with only the existing exact concurrency.queue compatibility exclusion.
  Earlier default actionlint runs alone did not prove ShellCheck was present.
- Complete Portal check exited 0, including 42 built routes and internal links;
  `/tmp/lmdj-cutover-post872-portal.log`.

These are local integration results, not O1 or O2 completion. C3's actual
running-process cancellation and fresh replay are separately recorded by
PR #868; the older expiry-race observation remains historical, not the final
interruption proof. Exact full-candidate acceptance and execution-enabled
missing-debt recovery still require their actual far-side evidence before
activation. Refresh the finite legacy inventory at the eventual cutover.

## Integration after PR #893 — still on HOLD

The local Task is rebased onto `3c2211c8336791956107aa67fe4ff9f1e40b3944`.
Backup branch `docs/ci-trigger-cutover-pre-layout` preserves the exact previous
`3d7dc35a83d98b806f6a943a6e65012b66ca979e` preparation. The two Portal source-path
conflicts retain both the relocated `docs/plans/` paths and all incremental
source declarations; the governance link uses `docs/design/`. This plan moves
to `docs/plans/` without recreating the retired directory. Both current scope
policies from PR #893 remain unchanged.

All results above are historical results for their named revisions, not proof
that this integrated tree passed. Fresh validation is recorded below before
completing the rebase. No product code, test threshold, permission, source
authentication or sixteen-suite inventory is relaxed. No push, PR, merge,
activation or remote exercise is authorized by this local integration.

Fresh integrated working-tree checks before rebase continuation:

- Complete CI Python inventory: 1,665 passed, no skips, 35.647 seconds;
  `/tmp/lmdj-cutover-layout-ci.log`.
- Staged ownership: 66 passed; `/tmp/lmdj-cutover-layout-ownership.log`.
- Repository-wide actionlint 1.7.12 with explicit ShellCheck 0.9.0 passed,
  retaining only the existing exact concurrency.queue syntax compatibility
  exclusion; `/tmp/lmdj-cutover-layout-actionlint.log`.
- Complete Portal check passed: 65 tests, documentation/diagram/source-fact
  validation, release-document checks, typecheck, 42-route build and valid
  internal links; `/tmp/lmdj-cutover-layout-portal.log`.
- All three changed skills passed skill-creator's quick validation. AGENTS and
  CLAUDE remain byte-identical. Staged whitespace passed. The execution and
  controller workflows, incremental entry and hosted-runner policy are
  byte-identical to the preserved T5 preparation; both canonical scope policies
  are byte-identical to the new main baseline.

These are local checks only. Historical candidate acceptance does not prove
current-main health; C3 recovery settlement and O2 platform-chain recovery remain
separate evidence boundaries. This integration neither dispatches nor publishes.

## Fixed Build 44 integration — activation remains on HOLD

The same Task is integrated once onto fixed main
`ed42b46faa539f0ead8c161d5ee54b70b2193c40`, without following later main changes.
Backup `docs/ci-trigger-cutover-pre-build44` retains exact
`77087e4aeed15506afba5e3806bea24cd4cefd8f`. Rebase had no conflicts. All 34 declared
paths remain the same; Build 44 product identities, Contract/CTest fixes and
immutable Portal snapshot from PR #894, plus PR #895/#896 documentation, remain
unchanged. Current testing/release pages retain both their new Build 44 facts
and the T5 control instructions. No frozen snapshot is rewritten.

Fresh integration verification (before the final evidence-only plan amendment):

- Complete CI contracts: 1,665 passed, no skips, 36.865 seconds;
  `/tmp/lmdj-cutover-build44-ci.log`.
- Ownership: 66 passed; `/tmp/lmdj-cutover-build44-ownership.log`.
- Repository-wide actionlint 1.7.12 with explicit ShellCheck 0.9.0 passed;
  `/tmp/lmdj-cutover-build44-actionlint.log`. Only the existing exact
  concurrency.queue syntax compatibility exclusion remains.
- All three changed skills passed quick validation; AGENTS/CLAUDE are identical.
- Complete Portal check on the stable integrated tree passed: 65 tests,
  39 current source pages, 10 diagrams / 20 outputs, source facts, release-doc
  validation, typecheck, 42 built routes and valid internal links;
  `/tmp/lmdj-cutover-build44-portal-final.log`. An earlier complete pass exists,
  but this second run explicitly began after rebase completed.
- Executable workflows, CI scripts and CI contracts are byte-identical to the
  preceding T5 preparation. Product/Contract/CMake and frozen Portal snapshot
  paths are byte-identical to the fixed new main baseline.

Prior results for Build 43 remain historical. This local integration does not
claim that C3 settlement/reporting or O2 has completed, and authorizes no
push, PR, merge, activation, product execution or release.

## O1 gate evidence accepted; O2 remains pending

The root and independent auditors completed the actual C3 recovery journey:

- Recovery executor `34182418092/1` produced a complete sixteen-suite verdict:
  fifteen passed and Creator failed, not sixteen passes. Original ZIP SHA-256
  `2f08cd256d1b11a4e1e52bce66e6a57a0db81dd3361c1dcd15fd62ff789a16fb`;
  evidence digest `63c8a24d690c0f0dc6cf695b90c3a0953129cf3205c6be0aa04c143070ece4f7`.
  Original material: `/tmp/lmdj-C3-terminal-independent.uvp4iziv`.
- Ordinary settlement `34185676231/1` authenticated generation 11 with no
  remaining coverage debt and the real Creator failure retained. Fresh replay
  `34185995655/1` preserved all eleven records and the complete state unchanged.
  Evidence: `/tmp/lmdj-C3-settle-independent.wx08lgj5` and
  `/tmp/lmdj-C3-replay-independent.3g_e_6zo`.
- Final report `34186045987/1` delivered the actual Creator observation to
  [Issue #865 comment 5579060281](https://github.com/endaye/lmdj/issues/865#issuecomment-5579060281).
  `/tmp/lmdj-o1-C3-final-report.br7HM7` retains complete 204-event authentication,
  the unchanged original 200-event prefix and fifty old deliveries, and the new
  exact positive HTTP receipt. All 51 currently queued observations are delivered;
  this does not claim delivery of future observations. The root independently
  repeated the final assertions.

[PR #892](https://github.com/endaye/lmdj/pull/892) retains candidate 02's actual
sixteen-pass verdict and canonical complete consumer acceptance for historical
target `0fedd7268e5f0f9a27390c3d8085387083f46e86`. That acceptance is not current-main
health, does not clear newer failures and authorizes no version or release.
The C3 failure is visible evidence, not a reason to restore a full-green merge
gate. The full O1 ledger is [the retained evidence record](2026-09-08-lmdj-ci-incremental-o1-evidence.md);
the later C3 evidence appendix is shipped independently by the root.

Fresh finite legacy inventory through `2026-09-08T03:39:31Z` retained 38 runs /
41 exact attempts, no in-flight legacy producer, two applicable sources and
three actually delivered observations; four non-main sources were explicitly
rejected. Original GET-only evidence is `/tmp/lmdj-legacy-migration-fresh.0tDvik`.
The root will briefly refresh both new runs and existing run attempt ceilings,
then verify live protection/review before shipping. O2 still requires actual
workflow_run chain-limit, independent health-tick recovery and idle/no-heavy
evidence after activation; neither these local checks nor O1 replace it.
