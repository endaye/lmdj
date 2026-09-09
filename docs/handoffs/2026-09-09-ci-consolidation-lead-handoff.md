# CI consolidation program: lead handoff

Living document. Updated by the current coordinator at every acceptance
milestone so that another coordinator can take the lead at any moment. Dates
are Asia/Shanghai, 2026-09-09 unless stated. Verify every state claim live
before acting; this file records what was true when it was written.

## 1. Who takes over and why

Trigger: the owner's weekly Claude token budget reaches 90 percent. The current
coordinator (Claude, Fable 5.1) then stops dispatching, updates this file, and
hands the lead to a Codex coordinator (`gpt-6-astra`, effort `high`) that
binds to the same Orca Run. Nothing about the program's goal, rules, or
authorization changes with the handoff.

Program authority and rules live in
`docs/plans/2026-09-09-lmdj-ci-consolidation.md` (merged at `8d7c79fc`, PR
#1090) and umbrella Issue #1089. Read the plan first, then this file, then
`AGENTS.md`, `docs/governance/git-workflow.md`,
`.agents/skills/issue-done/SKILL.md`.

Coordinator goal, verbatim from the owner:

> 你是 LMDJ 仓库 CI 整理程序的负责人，绑定 Orca Run `run_71c2492cd783`、
> umbrella Issue #1089、计划 `docs/plans/2026-09-09-lmdj-ci-consolidation.md`。
> 你只写 spec、拆 Task、起 Codex worker、验收结果，不亲自实现。每个 Task 一个
> PR，走 issue-done。验收标准是你在 worker 的 worktree 里重跑该 Task 的最低层验证
> 并读完合并后的 PR，不接受 worker 的口头声明。遇到计划里的 D1 到 D4 决策门必须等
> owner 拍板。禁止任何 release、deploy、journal reset、readiness 开关、增加
> hosted 花费。

## 2. Take the lead (commands)

```bash
orca status --json
orca orchestration run-use --run run_71c2492cd783 --json      # bind this terminal as coordinator
orca orchestration task-list --brief --json
orca orchestration worker-list --json
orca orchestration inbox --json                                # unread questions/escalations
orca orchestration check --wait --types worker_done,escalation,question --timeout-ms 570000 --json
```

Rules the previous coordinator learned the hard way (all observed today):

- Workers re-send an `ask` roughly every 20 seconds until answered; reply to
  every duplicate thread, and also `send --to dispatch:<ctx>` so the answer
  cannot be missed.
- Orca creates worker branches as `endaye/<name>`. Governance requires
  `fix/<task>`, `feat/<task>`, `docs/<task>`. Tell each worker to
  `git branch -m fix/<task>` before its first push. For an already-open PR,
  rename on GitHub with
  `gh api -X POST repos/endaye/lmdj/branches/<old, url-encoded>/rename -f new_name=fix/<task>`
  (the PR follows), then rename locally and reset the upstream.
- Workers merge autonomously unless told otherwise. Every spec now says: stop
  before `gh pr merge`, `ask` the coordinator with PR number, head SHA, review
  evidence and full `ci_*` counts, and merge only on "merge" with
  `--squash --match-head-commit <sha>`.
- The automated PR review (`pr-review.yml`) fails on nearly every head today
  (all three backends `runtime_failure`). Do not wait on it to succeed. Run an
  independent read-only reviewer (a separate agent that did not write the
  code) over the exact head, then post the record with
  `gh pr review <n> --comment --body-file <file>` following the format used on
  PR #1090 and #1092. Never let a worker self-review count as evidence.
- Pinned actionlint 1.7.12 for macOS is at
  `/private/tmp/claude-501/-Users-endaye-orca-workspaces-lmdj-bug-ci-snapshot-pitfall-uses-unknown-docs-area-a/218ace66-b422-49da-bdee-e7a6fd8c1db0/scratchpad/actionlint/actionlint`
  (darwin_arm64 archive SHA-256
  `aba9ced2dee8d27fecca3dc7feb1a7f9a52caefa1eb46f3271ea66b6e0e6953f`). That
  path is session-scoped and may vanish; re-download v1.7.12 and verify the
  checksum file before reuse. Export it as `LMDJ_ACTIONLINT` for the full
  `ci_*` discovery.
- Bash tool calls are capped at 10 minutes. Full `ci_*` discovery on this Mac
  can exceed that; run it detached (`nohup ... > log 2>&1 &`) and poll the log.
- Acceptance means: `git -C <worker worktree> status --short` clean, HEAD equals
  the PR head, the Task's lowest-tier verification re-run by the coordinator
  with counts, the merged PR body and review record read.

## 3. State at last update

Last updated: 2026-09-09 15:40 by Claude.

### Merged

| PR | Task | Merge SHA | Review evidence | Notes |
| --- | --- | --- | --- | --- |
| #1090 | plan | `8d7c79fc` | independent takeover on `fcc874ef` | automated runs 34367092851, 34368503521 failed |
| #1092 | P1.2 #1088 | `dae1cac2` | none at merge; post-merge independent review being recorded | worker merged before the merge-gate instruction reached it; branch kept `endaye/` prefix |

### Open PRs

| PR | Task | Head | State | Next step |
| --- | --- | --- | --- | --- |
| #1095 | P1.4 publish-release verify-published | `ef5e71e4` | worker done, merge held | coordinator re-ran `release_*` discovery, topology, ledger, actionlint (see §4); independent review in progress; then merge with `--match-head-commit` |
| #1097 | P1.1 #1078 pitfall area | `83d591e8` | worker active, review run 34370145086 in progress | worker asks merge/hold after review evidence |

### Worktrees and workers

| Task | Orca task | Dispatch | Worktree | Branch | State |
| --- | --- | --- | --- | --- | --- |
| P1.1 | task_aed1e9070a16 | ctx_dcd339eb39ac | `/Users/endaye/orca/workspaces/lmdj/fix-pitfall-snapshot-area` | `fix/pitfall-snapshot-area` (renamed on GitHub 15:38) | dispatched |
| P1.2 | task_5e703ee98cef | ctx_f1d946aa4b92 | `.../fix-canary-fixture-contract-profiles` | `endaye/fix-canary-fixture-contract-profiles` | completed; terminal not yet released |
| P1.4 | task_3302700a491d | ctx_5f70e14ca726 | `.../fix-publish-release-post-publish-verify` | `fix/publish-release-post-publish-verify` (renamed 15:30) | completed; merge pending coordinator |
| P2.1 | task_3294ba685655 | ctx_5e43ec6ab4f6 | `.../fix-retire-merge-queue-gates` | `endaye/fix-retire-merge-queue-gates` (rename before push) | dispatched; scope widened, see §5 |
| P2.2 | task_abf0a27a954f | ctx_9bc8f6bb130d | `.../fix-remove-pre-heavy-gate` | `endaye/fix-remove-pre-heavy-gate` | completed without shipping (commit `25988d2f`) |
| P2.2b | task_ce9ed533144d | ctx_a1fcf060ffb4 (terminal `term_b3f2a29d-0b7a-47f1-907a-72ac25091cba`) | same as P2.2 | rename to `fix/remove-pre-heavy-gate` | dispatched: full discovery, ship, ask before merge |

All worker specs were composed from a common rules block plus a per-Task
section; the per-Task content is reproduced in §5 so a new coordinator can
re-dispatch a Task verbatim.

### Owner decisions

D1 (PR advisory `ci_contract`+`docs_static` lane), D2 (freeze canary
`workflow_run` trigger), D3 (merge requires published review or explicit
`review:skipped` label), D4 (#1056 shared character allowlist): all
**pending**. Coordinator recommendations are in the plan. Do not start P1.3,
P2.3, P4.2 or Phase 7 until the owner answers. When the owner answers, record
the outcome in the plan's decision table via a `docs/` Task.

### Issue hygiene owed by the coordinator (not workers)

- Post the post-merge independent review on #1092.
- Close #1088 if the PR's closing keyword did not (check `gh issue view 1088`).
- Close already-fixed Issues with the proving commit: #906 (`c8736be3`, #909),
  #988 (`41a5a912`, #991), #944 (`1d72912e`, #984), #744 (gate condition can no
  longer be true; see plan "Why"), #591 (objective met, closing review comment
  2026-09-06).
- Label storage Issues #807 #817 #849 #824 #825 #826 #840 #857 `ci:storage`
  (create the label first) and update `.agents/skills/issue-list/SKILL.md` to
  exclude it (P3.3).
- After P3.1 merges, close the sixteen `missing` Issues #874–#879, #881–#890.
- Release settled worker terminals: `orca orchestration worker-release --dispatch <ctx> --json`.

## 4. Verification the coordinator has run

- P1.4 worktree at `ef5e71e4`: `git status` clean; `release_*_test.py`
  discovery, `ci_workflow_topology_test.py`, `ci_pitfall_ledger_test.py`
  (expected: only the #1078 failure until #1097 merges), pinned actionlint on
  `publish-release.yml` OK, `git diff --check origin/main...HEAD` OK. Counts
  are in the coordinator's transcript; re-run if in doubt.
- P1.2 worktree at `df7e71cc`: `ci_canary*_test.py` discovery re-run started
  15:31 (worker reported 320 passed, 1 skipped).
- P2.2 worktree at `25988d2f`: full `ci_*` discovery started 15:12 with pinned
  actionlint; result not yet read.

## 5. Task specs for re-dispatch

Common rules block (append to every spec):

```text
- You are in a fresh worktree created from origin/main. Verify with `git status --short` and `git log --oneline -1`. Never touch `main`.
- Read AGENTS.md, docs/governance/git-workflow.md, docs/governance/minimization-principle.md and .agents/skills/issue-done/SKILL.md before editing. Search .agents/pitfalls/ for open entries matching the Task's area labels.
- One Task = one Conventional Commit of exactly the declared files. If the declaration is wrong, stop and `orca orchestration ask` the coordinator; do not silently add files.
- Rename the branch before the first push: `git branch -m fix/<task>`.
- Red-first: the regression test must fail for the stated reason before the fix and pass after; report both runs.
- Never lower a threshold, widen a timeout, skip or delete a test, or de-select a lane to get green.
- Ship through issue-done: Task tests, staged-file inspection, `git diff --cached --check`, push, PR with every governance declaration, current-head review evidence per §5 (if the automated run fails, record the §5.3 takeover).
- STOP before `gh pr merge`: `orca orchestration ask --question "<task> ready to merge: PR #<n> head <sha>; review evidence: <what>; full ci_* result: <counts>" --options "merge,hold"`. Merge only on "merge", with `--squash --match-head-commit <sha>`.
- Do not close, relabel or comment on any GitHub Issue except through the PR's closing keyword for the Task's own Issue.
- Finish with exactly one `orca orchestration send --type worker_done ... --outcome succeeded|failed` carrying merged SHA or blocker, every verification command with counts, files modified, anything left undone.
```

Per-Task sections already dispatched (P1.1, P1.2, P1.4, P2.1, P2.2, P2.2b)
match the plan's ledger rows plus the following coordinator rulings:

- P2.1 widened: also owns `scripts/ci/github_queue_api.py` (move the data
  types it imports from `merge_queue.py` into it or a small
  `github_queue_types.py`, then delete `merge_queue.py`; delete
  `latest_label_event` if it has no live caller), `change_scope.py:1003`
  comment prose, `ci_scope_policy_consumer_parity_test.py` (queue lines only)
  and `ci_queue_evidence_mode_test.py`. Not its scope: `phase_gate.py`,
  `ci.yml`. Historical snapshots, pitfall entries, `docs/design`, `docs/plans`
  are never edited to satisfy the grep.
- P2.2 widened: every test referencing `pre-heavy-gate` / `phase_gate` /
  `batch-mode == 'false'`; update expectations, never loosen; leave queue
  files to P2.1; whichever of P2.1/P2.2 merges second rebases and reruns full
  discovery.
- P1.4 widened: the three current portal pages
  (`/operations/version-and-release/`, `/hosts/web-runtime/`,
  `/operations/testing-and-proof/`) with `Documentation impact: required`,
  `scripts/docs-site.sh install` then `check`; no snapshot regeneration.

Not yet dispatched (write the spec from the plan row plus the common block):
P2.3 (needs D1), P2.4, P3.1, P3.2, P4.1, P4.3, P4.4, P5.1, P5.2 (design
first), P6.1, P6.2, P6.3, P1.3 (needs D4), P4.2 (needs D3), Phase 7 (needs D2).
Suggested next wave once Phase 1/2 settle: P3.1 and P3.2 (independent files),
P4.1, P5.1. Keep at most five workers live; this Mac runs their test suites.

## 6. Process findings so far

- Two of the first three shipped Tasks (#1092, and #1090's own review) had no
  usable automated review. The program's D3 exists because of this; until the
  owner decides, the coordinator supplies independent takeover reviews.
- Worker #1092 merged without review evidence and without the merge gate; the
  gate was added to every spec afterwards.
- `worker_done` with `--outcome succeeded` was used by P2.2 for an unshipped
  Task; treat "succeeded" as a claim to verify, never as acceptance.

## Version Management

Version impact: none

Reason: handoff document only.

## Documentation Impact

Documentation impact: none

Reason: `docs/handoffs/` is not an Architecture Portal page.

Pitfall impact: none — process observations are recorded in §6 and in the
plan; no new mechanism.
