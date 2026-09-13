# Publication evidence branch transport

Status: delivery integration on merged PR #1281 base
`c1d5e8272e027e3058c5250c9425172f73d520a5`. This adapter depends on the
merged PR/workspace interfaces; the separately delivered source verifier is
not a dependency of this transport.

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

Historical original-stack results (commit `23538c73`, not this delivery):
13/13 branch tests passed (8.432 seconds), 23/23 PR regressions
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
Historical prerequisite observation: PR #1266 remained open at exact head
`c8fab3b67b6abe3bff708b5563acfc84b0e9e671`; this Task does not forge review adoption
or mutate the prerequisite. Local commit and remote shipping remain separate.

## Delivery repairs and revalidation

The imported branch suite passed 13/13 in 11.176 seconds on the merged base.
Before delivery, reduce the same durability boundaries previously repaired in
the PR controller: missing branch state must not reinitialize an unknown push;
encoded writes must fit the reader bound; and trusted callback exceptions must
not bypass secret-safe projection by sharing the local refusal exception type.
Add focused red regressions before implementation, preserve the existing real
Git process/crash journeys, and rerun all declared tests. Missing authoritative
state requires reconciliation, never automatic fresh enrollment or repeat push.
Do not claim automatic whole-journal-loss detection or clean failure artifacts.

All three pre-fix regressions failed as expected (two assertion failures and
one raw callback exception), then passed after the repairs. The durable empty
`branch-enrolled` marker is fsynced before initial state; a real fork exits in
that window and reopen refuses without a push. Existing-state marker absence,
nonempty marker and unsafe permissions are separate refusal regressions.
Oversized encoded state is refused before creating a temporary file, retaining
the previous state bytes and directory inventory. Invalid PR document capacity
is preflighted before enrollment. Trusted callback exceptions are projected to
the fixed unavailable result even if they use the local refusal exception type.

Delivery verification so far: branch 21/21 (14.612 seconds); the registered
CTest contract 1/1 (17.20 seconds, Python 3.14.7, unchanged 60-second timeout);
PR 36/36 and GitHub API 39/39; workspace 25/25 (44.270 seconds) and staged
ownership/admission 74/74 (7.194 seconds). Independent complete five-file review
found no actionable issues and separately ran 21/21 (15.177 seconds).
After locked `npm ci --ignore-scripts --no-audit --no-fund` with Node 22.22.2,
`scripts/docs-site.sh check` passed 144/144 tests, 47-page metadata, all diagrams,
snapshot consistency, typecheck, production build and 47 routes/internal links,
exit 0. PR body lint and documentation declaration passed. These are
temporary-remote/source checks, not canonical transport,
signer, hosted controller, deployment or release acceptance.

After PR #1281 merged, the unpublished delivery was rebased from `427d2a9f`
to `c1d5e827`. The sole conflict was the same CMake insertion point: retain
both source and branch contracts at their original 60-second bounds. Production
and test files are byte-identical across the rebase. Independent review
confirmed the complete five-file delta and original clean assessment remain
applicable. Reconfigured CTest passed both source (29.83 seconds) and branch
(16.84 seconds), 2/2; post-rebase ownership/admission passed 74/74 (5.999 seconds).
The post-rebase full Portal check also passed 144/144 tests, all prerequisite
validators/typecheck, production build and 47 routes/internal links, exit 0.

## Version Management

Version impact: none

Reason: internal release transport only; no Product Build or Assembly change.

## Documentation Impact

Documentation impact: required

Affected portal pages: /operations/version-and-release/

Reason: document the implemented exact-ref boundary and remaining integration.
