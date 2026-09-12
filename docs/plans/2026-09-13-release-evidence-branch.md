# Publication evidence branch transport

## Scope

Implement the missing local-commit → canonical remote branch leg before the
existing evidence PR controller. Reuse its closed operation spec. The trusted
caller must revalidate original authority, actual Task results, exact source
and effective protections; this transport never infers them from a digest.
Use a scratch bare Git config, the existing local object store, one exact SHA
and operation-bound ref. Require expected absence atomically at push. Durable
intent precedes push; an unknown result is observation-only on every retry.
An exact preexisting ref is adoptable, but a conflicting ref is never updated.
The Git child inherits the journal lock across controller death.

Declared files:

- `tools/release/evidence_branch.py`
- `tests/build/release_evidence_branch_test.py`
- `CMakeLists.txt`
- `apps/docs-site/docs/operations/version-and-release.mdx`
- `docs/plans/2026-09-13-release-evidence-branch.md`

## Verification

Use real temporary Git repositories and bare remotes, with fixture API identity
and authority gates. Assert exact far-side ref, preserved conflicting refs,
no extra refs, lost acknowledgements, delayed/missing results, pre-write gate
failure, scope rebound and private-state checks. Inject controller death and
prove a resumed operation does not blindly repeat a push. Inspect the production
Git command/environment for credential isolation and an absence lease.
Run the evidence PR regression, staged ownership, Portal check and independent
read-only review. No canonical push, PR, signer or deployment is exercised.

The real remote pre-receive hook also pauses an in-flight push while its
controller is killed. A replacement controller is refused by the inherited
lock; after allowing the original Git child to finish, the replacement observes
the exact remote SHA without another push. This proves the Git-process lease
leg in addition to before/after-effect controller crash cases.

Local results: 13/13 branch tests passed (8.432 seconds), 23/23 PR regressions
and 74/74 staged ownership tests passed. Independent read-only review inspected
all five declared files and independently ran 13/13 tests (8.149 seconds), with
no actionable finding. Logs: `/tmp/lmdj-evidence-branch-tests-v2.log`,
`/tmp/lmdj-evidence-branch-pr.log`, `/tmp/lmdj-evidence-branch-scope.log`.

The first Portal attempt failed because the new worktree lacked locked npm
dependencies, not because checks were skipped or relaxed. Retain
`/tmp/lmdj-evidence-branch-docs.log`; installed the existing lockfile with Node
22, `npm ci --ignore-scripts --no-audit --no-fund`, without manifest/lock edits.
The full Portal retry is recorded in `/tmp/lmdj-evidence-branch-docs-v2.log`.
It passed 139/139 tests, production build and 47-route/internal-link checks,
exit 0. No threshold, lane or test was relaxed. Python compilation and staged
whitespace validation also passed.

Pitfall disposition: consulted the credential and complete-journey entries;
no new process-only invariant or recurrence was exposed. The known credential
boundary is handled with one explicit token for both Git and the API, without
source-config/keychain fallback. These fixture results do not discharge the
unimplemented production gate/controller composition or real release journey.
The prerequisite PR #1266 remains open at exact head
`c8fab3b67b6abe3bff708b5563acfc84b0e9e671`; this Task does not forge review adoption
or mutate the prerequisite. Local commit and remote shipping remain separate.

## Version Management

Version impact: none

Reason: internal release transport only; no Product Build or Assembly change.

## Documentation Impact

Documentation impact: required

Affected portal pages: /operations/version-and-release/

Reason: document the implemented exact-ref boundary and remaining integration.
