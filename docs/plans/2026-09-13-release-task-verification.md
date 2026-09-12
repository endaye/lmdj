# Exact-source publication Task verification

## Scope

Implement the concrete local test receipt producer/reader required by the
publication branch and PR authority gates. Execute the three fixed Task checks
on the committed operation-bound evidence branch, after the existing workspace
precommit checks. Bind the request, operation, repository/actor, base, head,
tree, release identity and trusted control revision. A caller-supplied digest
alone is never a test receipt.

Before/after each command compare the entire committed checkout's raw bytes,
modes, symlink targets and index; do not trust Git stat/assume-unchanged flags
or clean filters. Source/authority admission remains a required trusted
callback before execution and reuse. Task execution has no inherited provider,
GitHub, signing, Python/Node injection or user-config environment. Dependencies
and PATH/toolchain are prepared by the trusted host, not installed by this API.
Only local `file` Git transports are available to the test commands, because
the real Portal suite creates shallow local-clone fixtures. The standalone
whitespace reader disables every transport and uses a scratch bare Git config,
fixed whitespace rules and the verified index; it does not read source-local
config or untracked `info/attributes`. The checkout is the raw Git blob form
(as created with `GIT_LFS_SKIP_SMUDGE=1`), not implicitly hydrated LFS content.

Durably record each command start, actual exit/output digest and verified-source
completion under one private writer lock. The child inherits that lock. Failed
or interrupted attempts are retained and never automatically rerun; a completed
receipt is reused only after validating every fixed command/result and binding.
Do not persist subprocess output text or expose arbitrary exception messages.
This is a trusted-local-service attestation, not proof against that same account
forging its own storage, and not GitHub review/protection or full release proof.

Declared files:

- `tools/release/task_verification.py`
- `tests/build/release_task_verification_test.py`
- `CMakeLists.txt`
- `apps/docs-site/docs/operations/version-and-release.mdx`
- `docs/plans/2026-09-13-release-task-verification.md`

## Verification

Real temporary Git worktree and subprocess checks: successful sequence/reuse,
nonzero command, death after launch, exact-head/tree/branch drift, masked dirty
bytes, symlink/mode drift, changed command/receipt, secret environment isolation,
invalid ownership and concurrent writer. Fixture check scripts prove process and
receipt behavior only; separately run actual repository Task tests and Portal.
Run staged ownership, existing workspace/branch/PR regressions and independent
read-only review. Do not push, create PRs, sign, publish or deploy in these tests.

## Results and retained failures

Final fixture suite: 15/15 passed, exit 0, 12.896 seconds, recorded in
`/tmp/lmdj-task-verification-tests-v4.log`. It includes real controller death
after a command, an orphaned command retaining the writer lock until exit,
and timeout process-group termination with no replay. Existing regressions:
workspace 19/19, branch 13/13, evidence PR 23/23 and staged ownership 74/74
passed (`/tmp/lmdj-task-verification-{workspace,branch,pr,scope}.log`).

Independent review found a real whitespace false-green: untracked local
`core.whitespace` can disable trailing-space detection while the tree stays
identical. The repaired scratch Git reader also excludes `info/attributes`.
The causal regression proves both ordinary-Git bypasses first, then confirms
the production checker returns exit 2. Independent rereview ran all 15 tests,
exit 0, and reported no remaining actionable finding.

The production executor itself ran the real repository Portal command. Its
first attempt failed, exit 1, because denying all Git protocols blocked the
suite's local shallow-clone fixture. Retain
`/tmp/lmdj-task-verification-portal-executor.log` and the separate diagnostic
`/tmp/lmdj-task-verification-portal-isolated-debug.log`. Allowing only local
file transport to test commands fixes that boundary without allowing external
Git transport; the standalone whitespace reader still denies every transport.

Real executor rerun: `scripts/docs-site.sh check` exit 0, output 42142 bytes,
SHA-256 `8d9292c1d3cda79b2e9bd1538087f904a8ff2cb508337981d1e7d6d7a267c28e`,
in `/tmp/lmdj-task-verification-portal-executor-v2.log`. The real ownership and
base-relative whitespace commands also passed through the production executor,
exit 0, in `/tmp/lmdj-task-verification-checks-executor.log`. These component
runs issued no publication Task receipt and did not pretend this implementation
branch was an authorized release-evidence branch. Command output is hashed,
not retained as raw text by the production receipt path. Python compilation and
staged whitespace checks passed. No test, threshold or lane was relaxed.

Pitfall disposition: the discovered execution defects are enforced directly
by this verifier and its causal regression; no distinct process-only rule is
introduced. Original authority/control/source admission, prepared dependencies,
effective protection, GitHub review and production-controller composition remain
required. No canonical PR/push, actual signing, deployment, promotion or complete
release journey was exercised. Local commit is not remote shipping acceptance.

## Version Management

Version impact: none

Reason: internal release Task verifier; no Product Build or Assembly change.

## Documentation Impact

Documentation impact: required

Affected portal pages: /operations/version-and-release/

Reason: distinguish actual locally executed receipts from remaining admission
and production-controller integration.
