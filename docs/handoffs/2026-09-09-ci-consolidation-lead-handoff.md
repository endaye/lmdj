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

## 1a. Immediate next actions for the incoming lead (in order)

1. Bind: `orca orchestration run-use --run run_71c2492cd783 --json`, then
   `orca orchestration inbox --json` and
   `orca orchestration check --wait --types worker_done,escalation,question --timeout-ms 570000 --json`.
   Five unread messages exist; the two pending `question`s from P2.2b
   (`ask` on PR #1100 at `cceba90b`) were already answered "hold" by Claude
   and are superseded by the worker's newer push; treat any new `ask` as live.
2. P2.2 (PR #1100, dispatch `ctx_a1fcf060ffb4`, worktree
   `.../fix-remove-pre-heavy-gate`): the remote head is now `71ddb7de`
   (worker rebased and pushed after the hold). Independent review of
   `cceba90b` found no must-fix; required follow-ups were sent (stale prose at
   `ci_workflow_topology_test.py` ~697 and `.github/scripts/retire_clean_review_threads.py:5`;
   PR body must declare the earlier-start scheduling effect and the now
   constant-false `check_documentation_impact`). When the worker asks:
   (a) `git -C <wt> status --short` clean and HEAD == PR head;
   (b) run `python3 tests/build/ci_workflow_topology_test.py`,
   `ci_runner_fallback_test.py`, `ci_hosted_runner_policy_test.py`, and the
   full `ci_*` discovery with `LMDJ_ACTIONLINT` (expect 0 failures / 0 errors
   on a head rebased past `9d4bf083`); (c) have an independent read-only agent
   diff `cceba90b..<head>` and confirm the follow-ups; (d) post the takeover
   record on #1100 citing run 34371885127 as failed; (e) merge with
   `--squash --match-head-commit`; (f) `worker-release --dispatch ctx_a1fcf060ffb4`.
3. P2.1 (PR #1103, dispatch `ctx_5e43ec6ab4f6`, worktree
   `.../fix-retire-merge-queue-gates`): head `9ed5a23b` reviewed, no must-fix;
   the worker is landing one follow-up commit (delete the now-dead
   `scripts/ci/github_queue_api.py` and update its two prose references;
   restore the `pr_gate` negative guards in `ci_pr_review_workflow_test.py:209`
   and `ci_benchmark_workflow_test.py:51,127`; drop the duplicate test in
   `ci_hosted_runner_policy_test.py:100`; fix stale "PR Gate" comments; correct
   the PR body). Same acceptance sequence as step 2; the automated run
   34373918902 on `9ed5a23b` failed. Whichever of #1100/#1103 merges second
   must rebase and rerun the full discovery before merge (both touch
   `ci_scope_policy_consumer_parity_test.py`).
4. Merge order matters: #1103 deletes `ci_merge_queue_workflow_test.py`, which
   asserted `ACTIONLINT_VERSION: 1.7.12`; that fact is still asserted by
   `ci_runner_fallback_test.py:304`, so nothing is lost.
5. After both merge: update the umbrella #1089 checklist (P2.1, P2.2), close
   nothing else automatically, and dispatch the next wave from §5
   (recommended: P2.4 stale prose, P3.1, P3.2, P4.1, P5.1 with the plan row
   corrected to name the controller's real HTTP module, and P1.2b).
6. Owner decisions D1 to D4 are still pending; ask the owner once, then record
   the outcomes in the plan via a `docs/` Task.

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
  `git branch -m fix/<task>` before its first push. Do NOT rename a branch
  that already has an open PR: on 2026-09-09 the GitHub rename API did not
  retarget PR #1095 (it stayed bound to the old name and could not receive
  the next push) and PR #1097 was closed by the worker in the confusion.
  Instead push under the new name, open a new PR with the same body and a
  "Supersedes #N" line, and close the old PR with a comment.
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

Last updated: 2026-09-10 00:45 (2026-09-09 16:45 UTC) by Claude. **Handoff executed at this time: the owner invoked the 90 percent trigger. Claude stopped dispatching; the Codex lead takes over from here.**

### Merged

| PR | Task | Merge SHA | Review evidence | Notes |
| --- | --- | --- | --- | --- |
| #1090 | plan | `8d7c79fc` | independent takeover on `fcc874ef` | automated runs 34367092851, 34368503521 failed |
| #1092 | P1.2 #1088 | `dae1cac2` | none at merge; post-merge independent review posted 15:47 (one low should-fix: `source_path` also admits `contracts/<family>/README.md`; follow-up P1.2b) | worker merged before the merge-gate instruction reached it; branch kept `endaye/` prefix; coordinator re-ran `ci_canary*` discovery in the worktree: 320 OK, 1 skipped |
| #1099 | P1.1 #1078 | `9d4bf083` | automated GLM review published on `83d591e8`, no findings | supersedes #1097, which the worker closed while renaming its branch; #1078 closed |
| #1101 | P1.4 verify-published | `0ecfb282` | independent takeover on `ef5e71e4` + delta `6d7dffc6` (4 should-fix applied) | supersedes #1095, which stayed bound to the renamed `endaye/` branch. Coordinator counts on `6d7dffc6`: release 439 OK, actionlint OK, whitespace OK, 11 declared files |

### Open PRs

| PR | Task | Head | State | Next step |
| --- | --- | --- | --- | --- |
| #1100 | P2.2 remove pre-heavy-gate | `71ddb7de` pushed 16:40 UTC (was `cceba90b`, base `c628f213`); not yet re-verified | independent review done on `cceba90b`: no must-fix; declare the earlier-start scheduling effect in the PR body; two stale-prose nits | HOLD until the worker pushes the rebased head with the nits folded in and a 0/0 full discovery; then coordinator re-checks the delta, posts the takeover record, merges |
| #1103 | P2.1 retire merge-queue/pr_gate | `9ed5a23b` (base `9d4bf083`) | independent review done: no must-fix; `scripts/ci/github_queue_api.py` has no live importer and must be deleted too; restore dropped `pr_gate` negative guards in two live-workflow tests; remove one duplicate test; stale "PR Gate" comments | HOLD until the worker's follow-up commit; then delta re-check, takeover record, merge. Plan row P5.1 names `github_queue_api.py`; correct it in the next plan docs Task (the controller's HTTP lives elsewhere) |
| #1098 | this handoff | living | n/a | merge at handoff or a stable milestone |

### Worktrees and workers

| Task | Orca task | Dispatch | Worktree | Branch | State |
| --- | --- | --- | --- | --- | --- |
| P1.1 | task_aed1e9070a16 | ctx_dcd339eb39ac | `/Users/endaye/orca/workspaces/lmdj/fix-pitfall-snapshot-area` | `fix/pitfall-snapshot-area` | completed (merged #1099); terminal released |
| P1.2 | task_5e703ee98cef | ctx_f1d946aa4b92 | `.../fix-canary-fixture-contract-profiles` | `endaye/fix-canary-fixture-contract-profiles` | completed; terminal released |
| P1.4 | task_3302700a491d / P1.4b task_80d177d14ee5 | ctx_5f70e14ca726 / ctx_101604f8d332 | `.../fix-publish-release-post-publish-verify` | `fix/publish-release-post-publish-verify` | completed (merged #1101); dispatches released |
| P2.1 | task_3294ba685655 | ctx_5e43ec6ab4f6 | `.../fix-retire-merge-queue-gates` | `endaye/fix-retire-merge-queue-gates` (rename before push) | dispatched; scope widened, see §5; ruling on four absorbed queue pitfalls: keep entries, add `tests/build/ci_retired_queue_mechanisms_test.py` asserting the removed files stay absent, re-point `gate:` exits to it, append a retirement paragraph |
| P2.2 | task_abf0a27a954f | ctx_9bc8f6bb130d | `.../fix-remove-pre-heavy-gate` | `endaye/fix-remove-pre-heavy-gate` | completed without shipping (commit `25988d2f`) |
| P2.2b | task_ce9ed533144d | ctx_a1fcf060ffb4 (terminal `term_b3f2a29d-0b7a-47f1-907a-72ac25091cba`) | same as P2.2 | rename to `fix/remove-pre-heavy-gate` | dispatched: full discovery, ship, ask before merge. Coordinator's own discovery on `25988d2f`: 2208 run, 4 failures, 7 errors (canary, gone after rebase); two failures are in `ci_runner_fallback_test.py` (fork-PR fallback assertion, mac gate routing) and were sent to the worker |

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

- Done 16:10: post-merge review on #1092; #1088 and #1078 closed by PR
  keywords; #906, #988, #944, #744, #591 closed with justification comments.
- Dispatch P1.2b (restrict `source_path` to `contracts/[^/]+/lmdj\.[^/]+\.v\d+\.md`,
  exclude README.md, one-reason test) once P1.4/P2.x settle.
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
- P1.4 counts: `release_*` 437 OK; topology 46 OK; change scope 66 OK; pitfall
  ledger 14/15 (the #1078 entry, now fixed on main).
- P1.2 worktree at `df7e71cc`: `ci_canary*_test.py` 320 OK, 1 skipped (755 s).
- P2.2 worktree at `25988d2f`: full `ci_*` discovery with pinned actionlint:
  2208 run, failures=4, errors=7, skipped=12 (1451 s); see the P2.2b row.
- P2.1 worktree at `9ed5a23b`: full discovery started 16:08 UTC; superseded
  when the follow-up commit lands. Quick checks by the reviewer all green
  (retired-mechanisms 2, topology 46, parity 5, change scope 66, ledger 15).

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
