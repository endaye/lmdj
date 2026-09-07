# Repair the rehearsal test's Git fixture

## Declared files

- `tests/build/ci_batch_runtime_workflow_test.py`
- This plan.

## Actual defect and boundary

O1 bootstrap run `34155431379`, CI contract job `101846325407`, failed the
new exact-JSON bridge test because it passed the CI repository ROOT to the
real execution adapter. CI correctly uses a shallow checkout for contract tests;
the execution adapter correctly refuses shallow provenance. A complete local
worktree had hidden the test's dependence on its surrounding Git history.

Create an isolated complete temporary Git fixture for this test. Continue to
load the actual policy, preserve exact output-to-input JSON assertions, and
invoke the real execution validator. Do not relax its shallow-history guard,
change the production checkout or replace provenance validation with a mock.
The existing execution tests still own rejection of shallow batch history.

## Verification

The original failure is retained in the actual O1 job log. Run all ten workflow
bridge tests and complete CI contracts, including from a real depth-one clone
of the final commit. Check staged ownership and whitespace. Real O1 execution
must still be settled; a local fixture repair does not turn its red run green.

Actual verification: ten targeted tests and 1343 complete CI contracts passed
with pinned actionlint available and no skips; 66 staged ownership tests passed.
A real depth-one clone (confirmed by Git) of the repaired code also passed all
1343 CI contracts. The production shallow-rejection guard is unchanged.
`scripts/architecture-portal.sh check` was attempted: 54 tests passed and three
failed due to absent isolated dependencies (`glob`, `gray-matter`, `cheerio`).
No Portal pass is claimed, and this Task changes no Portal files.

## Documentation Impact

Documentation impact: none

Reason: CI test fixture only; no Portal routes or automatic trigger changes.

## Version Management

Version impact: none

Reason: no product behavior or identities, tags, Release or deployment changes.

Pitfall impact: none — the test's environment dependence is fully captured by
isolated Git setup and actual shallow-clone verification; no new platform
permission or product invariant is inferred.
