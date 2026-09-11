# PR-Agent literal-space patch-header compatibility repair

Date: 2026-09-11
Status: lead-approved source-only Task; no host/model admission.
Relates to #1149, #1151, #1153 and #1154; their full acceptance remains pending.

## Outcome and ownership

The complete-input producer's real-Git experiment found that the existing T2
validator rejects a supported literal-space filename. Keep that supported
input case; repair the exact header grammar without rewriting the collected
diff or weakening path/digest/partition/RIGHT validation.

Lead owns this specification and independent acceptance. A Luna worker owns
one isolated `fix/pr-agent-space-headers` Task starting from freshly verified
main. The current known main is `ed4afbcb5003be9879c52c42fa2f15e1695cc4c5`;
lead will resolve the actual starting revision before dispatch. Read actual
AGENTS.md/CLAUDE.md and issue-done before editing. No nested agents.

Only these repository files are writable:

- `scripts/ci/pr_agent_review.py` — narrow patch-path header validation only.
- `tests/build/ci_pr_agent_review_test.py` — real-Git red reduction and focused
  positive/adversarial authentication regressions.
- `docs/plans/2026-09-11-pr-agent-space-header-repair.md` — exact copy of this
  approved plan, with no independently invented acceptance claims.

Own only NEW evidence files under
`/tmp/lmdj-pr-agent-plan/t4-space-header-repair-evidence-20260911/` outside the
repository. No producer/review_pipeline, public schema, workflow, dependency,
bundle, installer, config, budget, provider, credential, ledger, admission or
branch-protection changes. No SSH/sudo/systemd/provider/funding/model call,
secret access, GitHub write, push, PR or merge in this worker Task. No cleanup
of another directory, no overwriting/deleting/reconstructing earlier evidence.

## Reduced defect and exact intended grammar

For an addition named `add file.txt`, ordinary fixed Git diff emits a
`+++ b/add file.txt` header with one literal trailing TAB before LF. The
current `_verify_diff_semantics` requires the header without that delimiter.
This is normal Git output, not an unsupported quoted path or bad diff.

Primary upstream source confirms the rule in Git v2.54.0 `diff.c` lines
1476-1488: FILEPAIR_PLUS and FILEPAIR_MINUS append one TAB when the rendered
path label contains an ASCII space. See
[Git v2.54.0 source](https://github.com/git/git/blob/v2.54.0/diff.c#L1476-L1488).
Lead also verified actual local Git identity `2.54.0 (Apple Git-157)`.
Independently reproduce with a new temporary Git repository before fixing;
retain exact stdout bytes, current error and the unchanged input document.

Lead independently reproduced both defects through actual `authenticate_input`
at adapter SHA-256 `16526aa381a2dd6b20585676e5560c83679de200b3bdc4164486f3338876c6e8`:
`/tmp/lmdj-pr-agent-plan/t4-lead-header-reduction-actual-20260911.json` and the
adjacent diagnostic script. Actual Git space addition is rejected. A genuine
two-blob text diff containing header-looking source lines authenticates as a
positive baseline; changing only the real old/new metadata headers to an
unrelated path still authenticates because payload decoys satisfy the set
membership test. Every changed diff/hash is explicit; source was unchanged
across the run and no host/model call occurred. This is an input-validator
counterexample, not a claim of compromised GitHub publication authority.

Admit the existing exact no-delimiter header form for compatibility and the
native one-TAB delimiter form only for an otherwise exact allowed literal-space
path label. Never use broad strip/rstrip or whitespace tokenization. `/dev/null`
remains literal, with no suffix. Reject two TABs, a TAB on a no-space label,
appended timestamp/text, wrong side or path, extra path components, control
characters/quoted paths, and noncanonical prefixes. Do not broaden _safe_path.
Preserve the complete raw diff/hunk bytes and their existing hashes unchanged.

Read path-header metadata in its actual pre-hunk structural location, not from
a set of all payload lines: a deleted or added source line that merely looks
like `--- a/...` or `+++ b/...` cannot stand in for a header. Require unambiguous
old/new header identities where the change kind needs them; contradictory,
duplicate or missing headers cannot satisfy matching. Keep rename metadata,
binary/deletion semantics and existing malformed-partition refusals intact.
Do not add support for Git-quoted/control-character paths, metadata-only or
otherwise unrepresentable cases in this Task.

## Lowest-tier verification

Tests must not depend on the uncommitted new producer worktree. Construct a
small independent real-Git fixture with fixed object reads and actual emitted
diff, then build the existing T2 contract using independent expected blob and
RIGHT-line facts. The real `authenticate_input` must be the tested boundary.
No fake reviewer/authenticator and no test-only weakening of adapter guards.

1. Reduce the current failure before editing. Real Git object -> raw diff ->
   T2 document -> authentic input is a complete journey, with far-side byte,
   blob identity, file/hunk inventory and RIGHT assertions at every leg.
2. Independently cover additions, modifications, deletions, edited renames and
   pure renames with literal spaces, including directory spaces and trailing
   filename spaces. Cover old-space/new-no-space and the reverse for renames.
   Verify preserved CRLF and no-final-newline bytes when combined with spaces.
3. Keep the existing exact no-delimiter fixture form working. Cover regular
   no-space text, binary modifications and existing pure rename/deletion rules.
4. One-fact negative cases: duplicate/contradictory/missing old or new headers,
   wrong side/path/prefix, each suffix form above, header-looking payload decoys,
   renamed-path mismatch, and digest/blob/hunk/RIGHT tampering. When a negative
   fixture changes bytes, recompute unrelated hashes so it reaches the semantic
   check it claims to test; far-side failure yields no authenticated result.
5. Exercise the actual existing T3 collector-witness/trusted-collector seam with
   one accepted space-path input, and show a mismatched retained input fails.
   This remains an ordinary local consumer test, not a GitHub attestation.

Required commands: ordinary Python 3.11 full adapter suite; ordinary complete
review-pipeline, review-scope, and review-wait suites; staged new-file ownership
`python3 tests/build/ci_change_scope_test.py`; scope consumer parity and
differential suites; `scripts/docs-site.sh check` for the new plan/source facts.
Record exact command, interpreter and run/pass/fail/skip counts for EACH actual
invocation. The pinned handler integration may remain a separately named skip
under ordinary Python; do not count it as a pass or install new dependencies.
No runtime/provider behavior changes, so a bundle rebuild or paid run is not a
substitute for these precise input/consumer tests.

Follow issue-done before one Conventional Commit: verify compliant non-main
branch, tests, declared-path staging, inspect full staged diff, run staged
new-file ownership and diff --cached --check, commit, then verify exact commit,
tree, committed file list and clean final worktree. Run local-ci --list on the
whole committed range for classification only; do not change full-rule lane
selection. Return actual source/test hashes and all original failing commands.
Lead will independently review and ship after this local-only dispatch settles.

## Dependencies and remaining acceptance

This independent validator repair must land before the complete-input producer
can close its space-path acceptance leg. It changes future adapter source bytes,
not the already accepted inactive installed release or frozen T5 inputs/oracle.
The existing installed bundle remains at its previous identity and will not be
claimed to contain this change; any later bundle/stage transition needs its own
exact-candidate procedure. Do not rebuild or install now.

Continuous host publication/execution/collection supervision, recovery/capacity,
four-provider health/fallback, frozen offline quality evaluation, twenty live
current-head shadow runs, T6 cutover/rollback and operations handoff remain the
full migration requirements. No requirement or frozen denominator is reduced.

## Version Management

Version impact: none — an internal CI input-validator compatibility correction;
no Product, Module, Provider or public Contract manifest identity changes. The
future adapter file digest changes and must be bound by any later bundle.

## Documentation Impact

Documentation impact: none — this source-only internal grammar correction and
plan do not change a Portal route or deployed operation. The declared docs-site
check still runs; no host/provider/shadow acceptance is asserted.
