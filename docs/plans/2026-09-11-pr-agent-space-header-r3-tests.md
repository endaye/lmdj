# PR-Agent patch-header final independent test correction R3

Date: 2026-09-11. Lead-owned specification and acceptance; same Luna author.

## Outcome and scope

R2 Dispatch ctx_ccb6270c9f6b is settled and accepted as a corrective handoff,
not final branch shipping acceptance. Preserve R1/R2 commits and all evidence.
R2 HEAD 6e70ed5313d70535be8e9f7d415146a2a5607cc6, tree
a26ac8ed1799e43d906b85ee47531e58358692f2, is clean. Production adapter digest
3d0adb9123ca431200b3cc7c8df2c49f18f534a65a3bd2e1cf4b5739cb663855 has the
correct literal-LF framing. Do not change production code in this Task.

Continue in /Users/endaye/orca/workspaces/lmdj/fix-pr-agent-space-headers on
fix/pr-agent-space-headers. Exactly TWO writable repository paths:

- tests/build/ci_pr_agent_review_test.py
- docs/plans/2026-09-11-pr-agent-space-header-r3-tests.md: exact copy of this plan

NEW evidence only under /tmp/lmdj-pr-agent-plan/t4-space-header-r3-evidence-20260911/.
No other repository files, old plan/evidence rewrites, producer edits, nested
agents, SSH/sudo/systemd/model/provider/secret/funding actions, dependency
installs other than already-required locked docs npm ci, GitHub writes, push,
PR or merge. One NEW local Conventional Commit only; no amend or squash.

## Two reduced defects, all original requirements retained

1. R2 helper still starts from os.environ.copy() and removes only five GIT
   variables. The inherited GIT_CONFIG_COUNT/KEY/VALUE channel changes actual
   committed bytes. Lead ran the real test with core.autocrlf=true in that
   channel: baseline passed; the same CRLF fixture then failed because the
   base blob became b'old\nline\n' instead of b'old\r\nline\r\n'. This is a
   concrete fixture isolation defect, not a production header failure.
   FIRST run unchanged diagnostic
   /tmp/lmdj-pr-agent-plan/t4-lead-header-git-env-reduction-20260911.py and retain
   raw before evidence. Use an explicit minimal allowed Git environment, not
   a growing denylist; preserve fixed Git config/hook/template/signing/diff
   options and timeout. Include real regression running the same committed
   Git fixture with inherited config-count and config-parameters channels and
   repository locator variables poisoned, then proving exact expected Git
   object/raw-diff/blob/RIGHT facts still hold. Never change global config or
   execute attacker-provided hooks/filters. Keep required CRLF and no-final-LF
   data strict, not normalized by the test.
2. R2 specification required committed one-fact suffix regressions on both
   OLD and NEW no-space headers too. Current test loops all separators only
   on space paths, while no-space covers TAB alone. Complete the no-space
   old/new CR, VT, FF, NEL, LS and PS suffix cases, plain and TAB-followed,
   with a positive baseline first, refreshed unrelated hashes and semantic
   refusal. Preserve the entire existing space-path/decoy/real-Git cases and
   their independent facts; do not delete assertions or lower strictness.

Read original R1 and R2 specs fully; their scope of input behavior and all
acceptance legs remain mandatory. No additional feature or source refactor.

## Verification and local commit

After repair, unchanged environment diagnostic must pass BOTH cases, source
and test hashes unchanged across that run. Unchanged header-controls diagnostic
must retain both accepted baselines, all ten control suffix refusals, and the
payload-decoy negative refusal. Run ordinary Python 3.11 adapter, pipeline,
scope, wait, consumer parity, differential, staged change-scope suites and
docs-site check with PATH prefixed by
/Users/endaye/.nvm/versions/node/v22.16.0/bin. Record actual node/npm and each
invocation's discovered/run/pass/fail/skip separately. No pass credit for skips.
Run local-ci --list for full b9cb540fe7e1001e22569c0cbf48c7bb60426f02..HEAD
range as classification only. Read issue-done and follow exact-path staging,
staged diff/check, non-main check, commit inventory and final clean status.
Read and process ALL inbox messages, ACK your own delivery and check next until
empty at natural checkpoints and before worker_done; no stale FIFO replay.

Return exact new commit/tree/two-file inventory, source/test/plan digests, all
raw evidence paths and bounded claim. Lead will independently accept and land;
producer space-path dependency is not yet released. T4 host/recovery/capacity,
four-provider and frozen T5 14+20-head evidence, T6 cutover/rollback and ops
handoff remain unexercised and required, not replaced by these tests.

## Version Management

Version impact: none — test isolation/coverage only, no product identity.

## Documentation Impact

Documentation impact: none — no Portal route or deployed operation changes;
the required docs-site check still runs for the new Task plan.
