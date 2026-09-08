# Candidate policy preflight

## Scope and evidence

One Task prevents a queued candidate from spending full-suite capacity under a
policy that the existing candidate consumer will reject. Candidate request
`o1-full-candidate-0fedd-20260908-01` was genuinely queued by run
`34175608688/1`, frozen at control `fe043fd3a2a06dfbca4088cc59e0e8ef6997f336`
and policy `bc6834ca20b75872c42c92c3e5c5ac1fcc3d515889f4544cb37aff27620ea1c6`.
Read-only inspection after PR #846 found actual main
`e41daeab58d12c0c2cd243f1b29aad3055156ede` used policy
`8f7fe89afc960a0cda32a584d6697d14216b7e18d48e5400f73d16cbccd02c31` while all
four execution workflow blobs remained identical. This established a capacity
gap, not a remotely observed wasted candidate execution or successful candidate.

Declared files:

- `.github/workflows/ci.yml`: candidate-only policy comparison before heavy outputs.
- `scripts/ci/batch_runtime.py`: terminal incompatible candidate becomes missing.
- `tests/build/ci_batch_execution_workflow_test.py`: execute real inline workflow
  scripts against temporary Git commits, preserving auto/node semantics.
- `tests/build/ci_batch_runtime_test.py`: real Git plus strict HTTP fixtures,
  durable missing result, advance and fresh replay.
- This plan.

No new framework, schema, permission, trigger, release operation or T5 worktree
change. Keep all 16 suites, source4 authentication, exact run/attempt/main
ancestry and existing request validation. Do not mutate an already queued ID.
Root owns merge; this Task is authorized for local commit, push and PR only.

## Behavior and acceptance journey

For `candidate` only, the callee reads policy JSON from the exact actual executor
Git commit and compares its validated digest with the frozen request before
publishing execution outputs. Current trusted Python parses historical JSON;
no historical scripts execute. Unknown/malformed policy refuses preflight.
Automatic and node batches retain frozen-policy execution semantics.

The runtime authenticates the real terminal executor and existing source closure
before comparing its policy. A confirmed candidate mismatch returns missing;
unavailable policy or API/authentication errors remain errors. The normal durable
result/advance path releases the slot. Candidate settlement does not change
automatic processed progress, verification debts or historical failures.

The comparison binds executor control, not an indefinitely moving later main:
the candidate consumer still independently rejects later current-policy drift.
This is an early capacity check, never a release eligibility or publication grant.

Acceptance legs and far-side assertions:

1. Enqueue full candidate while bootstrap is active: frozen request enters queue.
2. Commit policy-only change with identical source4: later admission preserves
   the request and records the actual new executor claim.
3. Execute actual inline preflight: mismatch fails with why/remedy and zero heavy
   outputs; matching policy on another commit succeeds; auto/node remain valid.
4. A live executor remains pending, never fake-terminal. A policy read error
   remains an error, never evidence of absence.
5. Real runtime fixture receives terminal failed preflight without an artifact:
   all selected outcomes become missing and the active slot is released.
6. Even complete old-policy green three-file evidence is not a candidate pass:
   the same missing settlement retains nonempty automatic debt/failure history.
7. Fresh runtime replays the journal to the identical settled state without
   execution or repeated events.

The inline scripts use real temporary Git repositories. HTTP runs/jobs and
short-lock ownership remain fixtures, not remote O1 evidence. This Task does not
dispatch, cancel, rewrite the queued candidate, change Issue journals, or declare
full-passed acceptance. Real follow-up execution/settlement is separately owned.

## Verification

Red before fix: the real inline policy-only candidate test incorrectly emitted
heavy outputs; a complete old-policy runtime artifact incorrectly settled as
passed. Both were observed failing assertions before implementation. The
no-artifact runtime case already settled missing and is retained as a recovery
regression rather than falsely described as a new red.

Final local verification:

- Six targeted modules (execution workflow/runtime/controller/execution/verdict
  and release batch evidence): 261 tests passed, no skips.
- Full `ci_*test.py` discovery with `LMDJ_ACTIONLINT` set to pinned 1.7.12:
  1,663 tests passed, no skips. The initial run skipped its optional actionlint
  integration because that environment variable was absent; the final run
  exercised it rather than treating the skip as a pass.
- `ci_change_scope_test.py` after staging all five files: 66 passed.
- Pinned actionlint 1.7.12 on `ci.yml` passed with the existing exact
  `unexpected key "queue" for "concurrency" section` exception; raw invocation
  without that established exception reports the pre-existing queue schema.
- `git diff --cached --check` passed.
- `scripts/architecture-portal.sh check`: 54 passed, three failed because this
  isolated worktree lacks `glob`, `gray-matter` and `cheerio`. No dependency
  install, Portal build pass or remote acceptance is claimed.

Pitfall disposition: reviewed open CI/release entries and mandatory issue-done
guidance. This mechanically decidable policy eligibility/capacity mismatch is
fully captured by inline and runtime regressions; no new process-ledger entry or
recurrence is claimed. Broader fixture escalation #726 remains open.

## Version Management

Version impact: none — no Product Build, Module, Host, Provider or Contract
identity changes; no release intent, tag or publication operation.

## Documentation impact

Documentation impact: none — no Architecture Portal page, route, diagram or
projected product identity changes. This plan documents the narrow CI check;
the conservative workflow-source Portal check is still attempted and reported
honestly, not treated as a hidden all-portal merge requirement.
