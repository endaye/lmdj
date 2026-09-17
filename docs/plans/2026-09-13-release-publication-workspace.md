# R3: recoverable publication-evidence worktree execution

Status: delivery in progress on main `676874c3`, replaying `de32cb3b`.
Not shipped or enabled in a production release controller. Historical results
below are original-stack evidence, not this delivery's verification.

Delivery baseline and independent rerun passed the existing 19 tests. Independent
inspection nevertheless reproduced three uncovered defects: Git clean filters
can execute and conceal unrelated raw edits from diff/status; partial-clone
reads can hydrate missing objects; a real checkout interrupted by RLIMIT_FSIZE
leaves torn target bytes that OLD/NEW-only recovery refuses. New delivery
regressions reproduce the filter false-success and interrupted-write recovery
failure. The initial partial-clone regression refused the macOS `/var` root alias
before reaching Git; resolving the selected fixture root then reproduced actual
hydration (expected refusal absent). Git now disables lazy fetch and all protocols.
Raw streaming Git-blob hashes and modes now verify unrelated tracked paths
without diff/status, filters or index skip flags. Files are staged and fsynced
inside the owner-only journal on the same device, then atomically replaced and
both directories synced; incomplete staging is retained outside the worktree.
Actual RLIMIT_FSIZE failure and reopen now recover; a process-death regression
also covers immediately before/after the rename. Initial repaired suite passes
22/22. An additional unchanged-file regression showed Git `write-tree` itself
executing a clean filter; each invocation now inventories only configured driver
names and disables clean/smudge/process/required command-locally, including after
the verification callback. Expanded suite passes 25/25 (42.762s), independently
25/25 (43.414s), with no remaining actionable finding. Journal 21/21, publication
patch 19/19, staged ownership 74/74, clean Node 22.22.2 npm install and full Portal
144/144 plus production build and 47 routes/internal links pass. Existing npm
advisories remain 27 (9 moderate, 18 high), no unrelated audit fix. CMake config
passes with Python 3.14.7; registered CTest suite passes 1/1 in 42.90s without
changing its 60s timeout. Raw delivery command
returns are in the agent execution transcript, not original-stack logs below.
No physical power-loss or hostile same-UID concurrent writer guarantee is claimed.

## Scope

Turn the existing publication patch into an actual verified local Task commit
in a dedicated linked worktree. Use the full operation digest in the short-lived
`docs/release-evidence-…` branch, a private exclusive writer lock and an immutable
base/patch/tree/commit binding persisted before checkout. Reconstruct source
from immutable base blobs rather than partially written files. A private index
derives the exact five-file patch and deterministic Conventional Commit.

Only OLD or exact NEW bytes may be recovered. Unknown edits, unexpected staged
trees, untracked files, unsafe links/modes/attributes, wrong branch, rebound
operation and corrupt binding stop without overwriting those inputs. Ignored
tool outputs remain untouched. Do not run hooks or inherit injected Git config,
index, replace-ref or graft environment. Sync installed files, directories and
Git data before conditionally advancing the original branch. Rerun trusted
verification and check all bytes again even when reconciling an existing commit.
The Git subprocess inherits the writer-lock descriptor: controller death does
not permit a replacement writer to overlap an unfinished Git child. The child
must finish before a new writer may reacquire the lock and inspect the result.

The caller must provide fresh authenticated publication state, the original
durable request metadata and trusted Task verification (Portal and staged
ownership). Internal callback injection exists for tests, not user-selected
scripts or a verification bypass. This Task does not implement request intake,
worktree allocation, protected-main authentication, push, PR creation/review/
merge or the production backend. It creates no tag or public Release and makes
no deployment call. Those are still required by the overall design.

Declared files:

- `tools/release/publication_workspace.py`
- `tests/build/release_publication_workspace_test.py`
- `CMakeLists.txt`
- `apps/docs-site/docs/operations/version-and-release.mdx`
- `docs/plans/2026-09-13-release-publication-workspace.md`

## Verification

Real temporary Git and linked worktrees exercise source → partial install →
reopen → verification → conditional commit → reopen/reverify. Process-death
coverage exits immediately after the real ref write, then asserts the exact
commit is adopted once after lock reacquisition. Failed verification cannot
advance the branch. Source/old history and unrelated user files remain intact.
Use existing frozen publication fixtures; no provider, real GitHub write,
signer or deployment is exercised. The fixture verification callback checks
the real generated projection and staged whitespace, not the full Portal lane.
The implementation Task itself also runs the full Portal lane, staged ownership
and independent review. No existing threshold or check is reduced.

### Original-stack verification history

Initial
environment-injection test failed inside the fixture's own unsanitized Git
verification callback; switched that callback to the actual isolated runner,
retaining `/tmp/lmdj-publication-workspace-tests.log` and `-v2.log` failures.

Independent review found a binding initialization recovery gap. Replaced the
temporary hardlink sequence with atomic rename and adoption of exact complete
pending bytes. Both pre/post rename interruptions now recover; incomplete or
changed pending bytes remain an explicit retained conflict, never a guessed
operation. The orphan-child test uses real fork/process exit, pipe-blocked Git
and attempted lock reacquisition; it does not merely inspect subprocess args.
These logic/lifecycle invariants have direct regression coverage; no additional
process-only pitfall entry is introduced.

Final results (all exit 0): workspace/recovery 19/19, journal regression 19/19,
publication patch regression 16/16, staged ownership 74/74, Python compilation,
full Portal 139/139 tests and production build with 47 routes/internal links.
Independent reviewer `/root/release_journal_review` re-reviewed the binding
fix and child lock inheritance and independently ran all 19 tests; no remaining
actionable finding. Raw logs: `/tmp/lmdj-publication-workspace-tests-final.log`,
`/tmp/lmdj-publication-workspace-journal.log`,
`/tmp/lmdj-publication-workspace-evidence.log`,
`/tmp/lmdj-publication-workspace-scope.log`, and
`/tmp/lmdj-publication-workspace-docs.log`. The existing locked npm install
reported dependency advisories; no unrelated upgrade or audit fix was applied.
The local implementation stack remains behind PR #1266's unresolved owner
review-adoption boundary; this Task does not forge that adoption.

## Version Management

Version impact: none

Reason: internal release Task execution; no Product Build allocation, Assembly,
Module, Provider or public Contract identity change and no snapshot mutation.

## Documentation Impact

Documentation impact: required

Affected portal pages: /operations/version-and-release/

Reason: distinguish recoverable local commits from reviewed remote publication.
