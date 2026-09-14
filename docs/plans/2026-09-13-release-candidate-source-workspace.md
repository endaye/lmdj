# Recoverable internal candidate source commit

Delivery base: `60a9ee59a5e7f685213f63a1b7cdd8097a70595a`.
Reapply Task `80778e421381be17edd7da1f0e813d10f30c0cfc`, preserving the
newer passive Git reader, bounded journal writer and persistent request aliases.
The shared installer also retains the newer atomic file replacement, raw
file/mode checks and per-invocation filter disabling; never restore the old
checkout-index installation or Git status/diff truth checks.

## Task and files

The official scripts/docs-site.sh version path requires HEAD to contain the
requested Product Build and requires a clean worktree. Persist and install the
four generated candidate source files into a deterministic internal source
commit before invoking that snapshot seam. This intermediate source commit is
not a completed cut Task and must not be pushed as one. A later complete cut
commit must include the official snapshot and preserve source provenance, then
follow reviewed PR/squash and the official post-squash witness path.

Declared files:

- tools/release/candidate_workspace.py
- tools/release/publication_workspace.py
- tests/build/release_candidate_workspace_test.py
- CMakeLists.txt
- apps/docs-site/docs/operations/version-and-release.mdx
- docs/plans/2026-09-13-release-candidate-source-workspace.md

Use the actual CandidateBuildMaterial producer and durable reservation. Require
the request-bound feat branch in a dedicated linked worktree. Reject hidden
index flags and checkout attributes. Construct the exact four-file tree using
a private index, bind base/material/tree/commit/operation durably before any
checkout, recover only exact OLD/NEW bytes, verify and expected-old update-ref.
Reuse the existing publication workspace installation engine rather than
creating another file-recovery implementation; its original suite must pass.
No branch, index or unrelated edit may drift while verification runs.
Check Git's effective worktree root before reserving a Build and during later
workspace checks: worktree-local core.worktree must not redirect installation.

Remaining parent obligations: original authority/control/main/baseline-CI,
canonical service storage, official snapshot generation and recovery, final cut
commit/PR/current-head review, guarded squash, witness and actual candidate
target proof. No real Build allocation, snapshot, remote PR, signing or deploy
is performed by this development Task.

## Verification

Actual Git linked worktree, actual reservation and canonical source generation.
Assert exact clean four-file source commit and unchanged main; resume invokes
verification without another ref update; failed verification keeps original
HEAD and recovers staged material; partial checkout recovers; actual process
death after ref update reopens the same commit. Reject changed binding,
unknown source/index edits, hidden flags, wrong branch/primary worktree and
verifier drift without overwriting user data or advancing a ref.

Register commit recovery, interruption recovery and safety classes separately
at the original 30-second per-registration contract budget, preserving every
case. Run the original publication workspace
suite, material suite, staged ownership and Portal. No generic full-PR gate.

### Current delivery evidence

Original-stack results are historical, not current-head acceptance.

- The old installer extraction patch did not apply to the newer atomic/raw
  installer and was rejected without modifying the shared file. The actual
  extraction retains `_install`, `_raw_identity`, filter disabling and the
  final raw workspace check unchanged.
- The old interruption fixture patched `checkout-index`, which the current
  atomic installer never calls: 1 failure, 6.719s, exit 1, retained in
  `/tmp/lmdj-candidate-source-delivery-seam-red-v1.log`. This is an obsolete
  test seam, not a failure of the production atomic installer. The corrected
  fixture delegates to actual `_install`, interrupts after two completed atomic
  writes, and asserts two NEW / two OLD files, original HEAD/index and resumed
  payloads. Focused green: 1/1, 8.108s, exit 0,
  `/tmp/lmdj-candidate-source-delivery-seam-green-v1.log`.
- Initial registered recovery group exceeded its 30-second limit; the other
  results are retained in `/tmp/lmdj-candidate-source-delivery-ctest-v1.log`.
  Run exit 8; safety 9/9, material 11/11 and unchanged publication workspace
  25/25 passed. Complete original child output is retained separately in
  `/tmp/lmdj-candidate-source-delivery-ctest-child-v1.log`.
  Keep the six cases but separate four commit/resume cases from two interrupted
  installation/process-death cases; safety retains its nine cases. Every group
  retains its 30-second limit. This adds a separate crash-test registration,
  not a larger timeout or a removed journey leg; total registration allowance
  is not claimed unchanged.
- AST comparison against original Task `80778e421381be17edd7da1f0e813d10f30c0cfc`
  proves the same 15 case names remain: recovery 4, crash 2, safety 9; exit 0,
  `/tmp/lmdj-candidate-source-delivery-test-inventory-v2.log`. This inventory
  check does not substitute for actual execution of all three registrations.
- Independent reviewer `/root/release_journal_review` inspected the complete
  six-file Task, including preservation of current atomic/raw protections, and
  found no actionable finding; the later registration split was independently
  checked with no omitted case or weakened assertion. Independently executed
  the effective-root refusal case: 1/1, 1.796s, exit 0; diff check passed.
  Local review is not owner adoption or live PR merge eligibility.
- Final CTest selection
  `^build\.release_(candidate_workspace_recovery|candidate_workspace_crash|candidate_workspace_safety|candidate_material|publication_workspace)$`:
  5/5, 130.79s, exit 0. Actual child counts: recovery 4, crash 2, safety 9,
  material 11 and original publication workspace 25, all passed with no skips.
  Log: `/tmp/lmdj-candidate-source-delivery-ctest-v2.log`; complete child
  output: `build/core/dev/Testing/Temporary/LastTest.log` in this worktree.
  CTest completed before the Portal build started.
- Staged ownership/admission after all six declared files were staged: 74/74,
  6.860s, exit 0; `/tmp/lmdj-candidate-source-delivery-scope-v1.log`.
- With Node 22 and locked dependencies, `scripts/docs-site.sh check` passed:
  144/144 tests, zero skips, 47 pages / built routes, exit 0;
  `/tmp/lmdj-candidate-source-delivery-docs-v1.log`. The generated
  `apps/docs-site/build/operations/version-and-release/index.html` contains
  the internal source commit, preserved installer protection and incomplete-cut
  boundary statements; explicit output check exit 0:
  `/tmp/lmdj-candidate-source-delivery-rendered-v1.log`.
  Local rendering is not live Portal publication or an allocated snapshot.

No original-authority intake, official snapshot, cut PR, remote mutation,
actual Product allocation, signer or Site operation is performed.
Pitfall disposition: real Git regressions express the workspace installation
and safety invariants directly; no new process-only ledger rule is claimed.

## Version Management

Version impact: none

Reason: workspace controller implementation; all candidate source commits in
verification live only in temporary fixture repositories, not a real release.

## Documentation Impact

Documentation impact: required

Affected portal pages: /operations/version-and-release/
