# PR-Agent patch-header repair R2

Date: 2026-09-11. Lead-approved corrective source-only Task.

## Settlement and target

R1 Dispatch ctx_95f76f15adf8 is settled; its report is accepted only as a
corrective handoff, NOT implementation acceptance. Preserve commit
bec789ea2ee808a6cb967017103cd6f33f045d6a and every R1 evidence file unchanged.
Continue in /Users/endaye/orca/workspaces/lmdj/fix-pr-agent-space-headers on
fix/pr-agent-space-headers. Same Luna author owns this new correction Task.
Lead owns spec, plan and independent acceptance. No nested agents.

Read original /tmp/lmdj-pr-agent-plan/t4-lead-space-header-repair-spec-20260911.md
fully: all original supported cases and acceptance legs remain mandatory.

## Exact writable ownership

- scripts/ci/pr_agent_review.py: narrow header framing/grammar correction.
- tests/build/ci_pr_agent_review_test.py: independent real-Git regressions.
- docs/plans/2026-09-11-pr-agent-space-header-r2.md: byte-exact copy of this plan.

NEW evidence only under /tmp/lmdj-pr-agent-plan/t4-space-header-r2-evidence-20260911/.
No other repo files, old evidence rewrites/deletion, producer worktree edits,
host/sudo/SSH/systemd/provider/model/secret/funding action, GitHub write,
push/PR/merge, dependency manifests/lockfiles, workflow or schema changes.
One NEW local Conventional Commit after all verification; no amend/squash of R1.

## Mandatory corrections (do not settle until each is evidenced)

1. FIRST reproduce the lead diagnostic unchanged:
   python3 -B /tmp/lmdj-pr-agent-plan/t4-lead-header-controls-reduction-20260911.py
   The exact committed R1 source SHA-256 is
   ad95110b5c84a3bf0999986dd3e8bc655da624a86302adcdecf5ad9ed302a7e1.
   Lead committed-source raw result is
   /tmp/lmdj-pr-agent-plan/t4-lead-header-controls-committed-r1-actual-20260911.json.
   BOTH valid Git baselines authenticate, but all 10 CR/VT/FF/NEL/LS suffix
   mutations incorrectly authenticate. section.splitlines() silently removes
   them before exact matching. Parse metadata with literal LF framing only;
   never strip other bytes. Preserve CRLF/no-final-LF PAYLOAD and all existing
   original-plan supported paths. Add one-fact tests on OLD and NEW metadata
   headers, including a no-space path and allowed space/TAB delimiter path;
   plain suffix and suffix following the allowed TAB must reject. Include PS
   and other splitlines separators where relevant. Positive controls pass first.
2. R1 test_payload_header_decoys_cannot_satisfy_real_metadata has invalid blobs:
   base/head hold three '-'/'+' characters but the hunk represents only two.
   Correct fixture bytes (prefer actual Git diff), prove unchanged metadata
   authenticates and its exact RIGHT/blob facts, THEN mutate ONLY real metadata
   with all unrelated hashes refreshed and show semantic rejection. A fixture
   that already rejects before mutation is not a regression proof.
3. Replace circular fixture construction: document_from_git_diff currently
   calls adapter._parse_diff_hunks and adapter._parse_patch_right_lines, copies
   unrelated fixture identity, and uses index-only cached diff after base.
   Build actual committed base/head/control identity, independently read exact
   Git blobs/object IDs/raw diff, and use hand-authored expected hunk/RIGHT facts
   for small fixtures. Assert far-side identity/bytes/complete inventory/hunks/
   RIGHT for EVERY original case: additions, modifications, deletions, edited
   renames both space directions, pure renames, directory/trailing spaces,
   CRLF and no-final-newline. Preserve legacy/native headers, binary and T3
   consumer positive/retained mismatch legs. No production parser as oracle.
4. Correct evidence accounting without rewriting R1: unittest 'Ran 50' with
   2 skips means 48 pass, NOT 50 pass. Record discovered/run/pass/fail/skip per
   invocation separately. R1 docs used Node 26 despite lead identifying Node22;
   run required docs install/check with task-local PATH prefix
   /Users/endaye/.nvm/versions/node/v22.16.0/bin. Record node and npm actual
   versions (bundled npm is 10.9.2; packageManager says 10.9.3). No global change
   or guessed alternate pin. Preserve failure output before retrying.

## Verification and shipping boundary

Run the entire original required ordinary Python adapter, pipeline, scope,
wait, parity, differential suites; staged ci_change_scope_test; docs-site check;
local-ci --list for the whole b9cb540fe7e1001e22569c0cbf48c7bb60426f02..HEAD
range (classification only). Re-run the unchanged lead diagnostic after repair:
2 valid baselines accepted, all 10 invalid suffixes rejected, payload-decoy
negative rejected. Bind results to exact source/test hashes before AND after.
Follow issue-done: declared-path staging, staged diff/check, non-main branch,
new local commit, committed inventory and final clean worktree. Read all inbox
messages at natural checkpoints and immediately before worker_done; follow-ups
are not optional. Return failure honestly if any required leg remains absent.

No bundle or installed-release acceptance is implied. Complete-input producer
cannot close its space-path dependency until lead accepts/lands this repair.
Full #1149/#1150-1155 host, recovery, capacity, four-provider, frozen T5 and real
shadow, T6 cutover/rollback/operations requirements remain unchanged.

## Version Management

Version impact: none — internal CI validator correction; no manifest identity.
Any future bundle must authenticate the changed adapter digest separately.

## Documentation Impact

Documentation impact: none — internal input grammar correction and Task plan;
no Portal route or deployed operation changes. Declared docs-site check runs.
